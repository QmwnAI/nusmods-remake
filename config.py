"""Application configuration — loaded from environment via python-dotenv."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "planner.db")

    # Auth
    CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "").strip()
    CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "").strip()
    CLERK_ISSUER = os.getenv("CLERK_ISSUER", "").strip()
    # Comma-separated list of allowed `azp` claim values (your frontend domain[s]).
    # Optional but recommended in production to prevent token replay from other origins.
    CLERK_AUTHORIZED_PARTIES = os.getenv("CLERK_AUTHORIZED_PARTIES", "").strip()

    @property
    def auth_dev_mode(self) -> bool:
        """If no Clerk key is configured, run in dev mode (accept fake tokens)."""
        return not self.CLERK_SECRET_KEY

    # NUSMods
    NUSMODS_BASE_URL = os.getenv("NUSMODS_BASE_URL", "https://api.nusmods.com/v2")
    NUSMODS_ACAD_YEAR = os.getenv("NUSMODS_ACAD_YEAR", "2024-2025")

    # CORS
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]


config = Config()
