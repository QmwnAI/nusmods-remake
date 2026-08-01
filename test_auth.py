"""Tests for auth.py — Clerk JWT verification.

Generates a real RSA key pair, signs fake JWTs, and exercises the verification
code path with an injected fake JWKS client. This catches all the verification
logic (signature, issuer, expiry, azp, claim extraction) without needing the network.

Run: python tests/test_auth.py
"""
from __future__ import annotations

import os
import sys
import time
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth import (
    _verify_clerk_token,
    _verify_dev_token,
    _extract_user_info,
)
from config import config


def assert_eq(a, b, label):
    status = "✓" if a == b else "✗"
    print(f"  {status} {label}: got {a!r}")
    assert a == b, f"{label}: expected {b!r}, got {a!r}"


def assert_raises(fn, exc_type, label, msg_contains=None):
    try:
        fn()
    except exc_type as e:
        if msg_contains and msg_contains not in str(e):
            print(f"  ✗ {label}: expected message containing {msg_contains!r}, got {e!r}")
            raise AssertionError()
        print(f"  ✓ {label}: raised {exc_type.__name__} as expected")
        return
    except Exception as e:
        print(f"  ✗ {label}: expected {exc_type.__name__}, got {type(e).__name__}: {e}")
        raise
    raise AssertionError(f"{label}: expected {exc_type.__name__}, got nothing")


# ---------------- Test fixtures ----------------

def _generate_key_pair():
    """Make an RSA key pair and a fake JWKS client that serves the public key."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    fake_client = MagicMock()
    signing_key = MagicMock()
    signing_key.key = public_key
    fake_client.get_signing_key_from_jwt.return_value = signing_key
    return private_key, fake_client


def _make_token(private_key, claims: dict, headers: dict | None = None) -> str:
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pyjwt.encode(claims, pem, algorithm="RS256", headers=headers or {"kid": "test-key-1"})


# ---------------- Tests ----------------

def test_dev_tokens():
    print("\n[dev token verification]")
    assert_eq(_verify_dev_token("dev-user-alice"), "dev-user-alice", "valid dev token")
    assert_eq(_verify_dev_token("dev-user-bob123"), "dev-user-bob123", "with suffix")
    assert_eq(_verify_dev_token("dev-user-"), None, "empty suffix rejected")
    assert_eq(_verify_dev_token("random-token"), None, "non-dev prefix rejected")
    assert_eq(_verify_dev_token(""), None, "empty token rejected")


def test_clerk_valid_token():
    print("\n[Clerk: valid token]")
    private_key, fake_client = _generate_key_pair()
    now = int(time.time())
    token = _make_token(private_key, {
        "sub": "user_2NxhTest",
        "iss": "https://test.clerk.accounts.dev",
        "exp": now + 60,
        "iat": now,
        "email": "alice@example.com",
        "name": "Alice Tan",
    })

    # Override issuer config so verification runs against our test value
    original_issuer = config.CLERK_ISSUER
    config.CLERK_ISSUER = "https://test.clerk.accounts.dev"
    try:
        user_id, claims = _verify_clerk_token(token, jwks_client=fake_client)
        assert_eq(user_id, "user_2NxhTest", "extracted sub")
        assert_eq(claims["email"], "alice@example.com", "email in claims")
    finally:
        config.CLERK_ISSUER = original_issuer


def test_clerk_expired_token():
    print("\n[Clerk: expired token rejected]")
    private_key, fake_client = _generate_key_pair()
    now = int(time.time())
    token = _make_token(private_key, {
        "sub": "user_x",
        "exp": now - 60,  # 1 min ago
        "iat": now - 120,
    })
    assert_raises(
        lambda: _verify_clerk_token(token, jwks_client=fake_client),
        ValueError,
        "expired token raises ValueError",
        msg_contains="expired",
    )


def test_clerk_wrong_issuer():
    print("\n[Clerk: wrong issuer rejected]")
    private_key, fake_client = _generate_key_pair()
    now = int(time.time())
    token = _make_token(private_key, {
        "sub": "user_x",
        "iss": "https://attacker.example.com",
        "exp": now + 60,
    })

    original_issuer = config.CLERK_ISSUER
    config.CLERK_ISSUER = "https://expected.clerk.accounts.dev"
    try:
        assert_raises(
            lambda: _verify_clerk_token(token, jwks_client=fake_client),
            ValueError,
            "wrong issuer raises ValueError",
            msg_contains="issuer",
        )
    finally:
        config.CLERK_ISSUER = original_issuer


def test_clerk_wrong_signature():
    print("\n[Clerk: bad signature rejected]")
    private_key_1, _ = _generate_key_pair()
    _, fake_client_2 = _generate_key_pair()  # serves a DIFFERENT public key
    now = int(time.time())
    # Token signed with key 1, verification will use key 2 → mismatch
    token = _make_token(private_key_1, {
        "sub": "user_x",
        "exp": now + 60,
    })
    assert_raises(
        lambda: _verify_clerk_token(token, jwks_client=fake_client_2),
        ValueError,
        "bad signature raises ValueError",
    )


def test_clerk_missing_sub():
    print("\n[Clerk: missing sub claim rejected]")
    private_key, fake_client = _generate_key_pair()
    now = int(time.time())
    token = _make_token(private_key, {
        # no sub
        "exp": now + 60,
    })
    assert_raises(
        lambda: _verify_clerk_token(token, jwks_client=fake_client),
        ValueError,
        "missing sub raises ValueError",
    )


def test_clerk_azp_validation():
    print("\n[Clerk: azp validation]")
    private_key, fake_client = _generate_key_pair()
    now = int(time.time())

    original_parties = config.CLERK_AUTHORIZED_PARTIES
    config.CLERK_AUTHORIZED_PARTIES = "http://localhost:5173,https://app.example.com"

    try:
        # Allowed azp
        token_ok = _make_token(private_key, {
            "sub": "user_x", "exp": now + 60, "azp": "http://localhost:5173",
        })
        user_id, _ = _verify_clerk_token(token_ok, jwks_client=fake_client)
        assert_eq(user_id, "user_x", "allowed azp accepted")

        # Disallowed azp
        token_bad = _make_token(private_key, {
            "sub": "user_x", "exp": now + 60, "azp": "https://attacker.example.com",
        })
        assert_raises(
            lambda: _verify_clerk_token(token_bad, jwks_client=fake_client),
            ValueError,
            "disallowed azp raises",
            msg_contains="azp",
        )

        # Token with no azp passes (azp is optional)
        token_no_azp = _make_token(private_key, {
            "sub": "user_x", "exp": now + 60,
        })
        user_id, _ = _verify_clerk_token(token_no_azp, jwks_client=fake_client)
        assert_eq(user_id, "user_x", "no azp accepted (claim optional)")
    finally:
        config.CLERK_AUTHORIZED_PARTIES = original_parties


def test_extract_user_info():
    print("\n[extract_user_info]")
    # email + name
    e, n = _extract_user_info({"email": "a@b.com", "name": "Alice Tan"})
    assert_eq(e, "a@b.com", "email")
    assert_eq(n, "Alice Tan", "name")

    # given/family fallback
    e, n = _extract_user_info({"email": "a@b.com", "given_name": "Alice", "family_name": "Tan"})
    assert_eq(n, "Alice Tan", "given+family composes name")

    # nothing
    e, n = _extract_user_info({"sub": "user_x"})
    assert_eq(e, None, "no email")
    assert_eq(n, None, "no name")

    # primary_email_address fallback
    e, _ = _extract_user_info({"primary_email_address": "b@c.com"})
    assert_eq(e, "b@c.com", "primary_email_address fallback")


if __name__ == "__main__":
    print("Running auth tests…")
    test_dev_tokens()
    test_clerk_valid_token()
    test_clerk_expired_token()
    test_clerk_wrong_issuer()
    test_clerk_wrong_signature()
    test_clerk_missing_sub()
    test_clerk_azp_validation()
    test_extract_user_info()
    print("\nAll tests passed ✓")
