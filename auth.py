"""Authentication.

Two modes, picked at startup based on whether CLERK_SECRET_KEY is configured:

1. **Dev mode** (default): tokens of the form `dev-user-<anything>` resolve to that user_id.
   The user row is auto-created on first request. Great for local development without Clerk.

2. **Production mode**: tokens are verified as Clerk JWTs:
     - Decode header to get `kid`
     - Fetch matching public key from Clerk's JWKS (cached, 10-min TTL via PyJWKClient)
     - Verify RS256 signature, issuer, expiration
     - Optionally validate `azp` (authorized party) against CLERK_AUTHORIZED_PARTIES
     - Extract user_id from `sub`, email/name from claims

Use the @require_auth decorator on any route. After auth, `flask.g.user_id` holds the
authenticated user_id and `flask.g.user` holds the user row as a dict.
"""
from __future__ import annotations

import functools
from typing import Optional

import jwt as pyjwt
from flask import request, jsonify, g
from jwt import PyJWKClient, PyJWKClientError

from config import config
from db import get_db


# ---------------- JWKS client (cached) ----------------

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    """Lazily build a JWKS client. Cached for process lifetime; PyJWKClient
    itself caches fetched keys with a configurable TTL.

    Built lazily so the import doesn't fail when CLERK_JWKS_URL is unset (dev mode).
    """
    global _jwks_client
    if _jwks_client is None:
        if not config.CLERK_JWKS_URL:
            raise RuntimeError("CLERK_JWKS_URL not configured")
        _jwks_client = PyJWKClient(
            config.CLERK_JWKS_URL,
            cache_keys=True,
            lifespan=600,  # 10 min cache. JWKS rotation is rare; this is a sensible TTL.
        )
    return _jwks_client


def reset_jwks_cache() -> None:
    """Drop the cached JWKS client. Tests use this between cases; production rarely needs it."""
    global _jwks_client
    _jwks_client = None


# ---------------- User row helpers ----------------

def _ensure_user_row(user_id: str,
                    email: Optional[str] = None,
                    display_name: Optional[str] = None) -> dict:
    """Insert a user row if missing; update email/display_name if newer info arrived."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if row is None:
        db.execute(
            "INSERT INTO users (id, email, display_name) VALUES (?, ?, ?)",
            (user_id, email or f"{user_id}@unknown.local", display_name or user_id),
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row)

    # Update if we have new info (e.g. Clerk JWT carries email, displaces the @unknown.local placeholder)
    updates: list[str] = []
    params: list = []
    if email and email != row["email"]:
        updates.append("email = ?")
        params.append(email)
    if display_name and display_name != row["display_name"]:
        updates.append("display_name = ?")
        params.append(display_name)

    if updates:
        params.append(user_id)
        db.execute(
            f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            params,
        )
        db.commit()
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    return dict(row)


# ---------------- Token verifiers ----------------

def _verify_dev_token(token: str) -> Optional[str]:
    """Dev-mode: any `dev-user-<anything>` token resolves to that user_id."""
    if token.startswith("dev-user-") and len(token) > len("dev-user-"):
        return token
    return None


def _verify_clerk_token(token: str, jwks_client: PyJWKClient | None = None) -> tuple[str, dict]:
    """Verify a Clerk JWT and return (user_id, full_claims_dict).

    Raises ValueError on any verification failure (expired, bad signature, wrong issuer, etc).
    Raises ConnectionError if JWKS is unreachable.

    The optional `jwks_client` parameter is for testing — injects a fake client that
    serves predetermined keys instead of fetching from Clerk.
    """
    client = jwks_client or _get_jwks_client()

    # Pull the signing key for this token's `kid`. PyJWKClient handles caching + auto-refresh
    # if it sees an unknown kid (handles key rotation gracefully).
    try:
        signing_key = client.get_signing_key_from_jwt(token)
    except PyJWKClientError as e:
        raise ValueError(f"Could not resolve signing key: {e}") from e

    # Decode + verify in one shot. PyJWT validates exp, iat, and (when given) issuer for us.
    decode_kwargs = {
        "algorithms": ["RS256"],
        "options": {"require": ["sub", "exp"]},
    }
    if config.CLERK_ISSUER:
        decode_kwargs["issuer"] = config.CLERK_ISSUER

    try:
        claims = pyjwt.decode(token, signing_key.key, **decode_kwargs)
    except pyjwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except pyjwt.InvalidIssuerError:
        raise ValueError("Invalid token issuer")
    except pyjwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}") from e

    # Optional: validate authorized party (azp). Clerk recommends pinning this to your
    # frontend domain(s) to prevent token replay from other origins.
    authorized_parties = [p.strip() for p in (config.CLERK_AUTHORIZED_PARTIES or "").split(",") if p.strip()]
    if authorized_parties:
        azp = claims.get("azp")
        if azp and azp not in authorized_parties:
            raise ValueError(f"Token azp {azp!r} not in allowed list")

    user_id = claims["sub"]
    return user_id, claims


def _extract_user_info(claims: dict) -> tuple[Optional[str], Optional[str]]:
    """Pull email and display_name out of Clerk JWT claims if present.

    Clerk's default session token claims include `sub`, `exp`, `iat`, `iss`, `nbf`, `azp`.
    Email is only present if you've added an `email` claim in the Clerk Dashboard's
    JWT template. We try a few common claim names.
    """
    email = claims.get("email") or claims.get("primary_email_address")
    display_name = (
        claims.get("name")
        or claims.get("full_name")
        or (
            f"{claims.get('given_name', '')} {claims.get('family_name', '')}".strip()
            if claims.get("given_name") or claims.get("family_name")
            else None
        )
    )
    return email, display_name


# ---------------- Decorator ----------------

def require_auth(fn):
    """Route decorator. Sets g.user_id and g.user on success, returns 401 otherwise."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="Missing or malformed Authorization header", code="NO_AUTH"), 401

        token = header[len("Bearer "):].strip()
        user_id: Optional[str] = None
        email: Optional[str] = None
        display_name: Optional[str] = None

        if config.auth_dev_mode:
            user_id = _verify_dev_token(token)
        else:
            try:
                user_id, claims = _verify_clerk_token(token)
                email, display_name = _extract_user_info(claims)
            except ValueError as e:
                return jsonify(error=str(e), code="INVALID_TOKEN"), 401
            except ConnectionError as e:
                return jsonify(error=f"Auth service unreachable: {e}", code="AUTH_UNAVAILABLE"), 503

        if not user_id:
            return jsonify(error="Invalid token", code="INVALID_TOKEN"), 401

        g.user_id = user_id
        g.user = _ensure_user_row(user_id, email=email, display_name=display_name)
        return fn(*args, **kwargs)

    return wrapper
