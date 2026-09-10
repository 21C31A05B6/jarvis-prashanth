"""Environment-backed configuration for the hosted API.

Configuration is intentionally environment-driven (never hard-coded) so that
development and production deployments can never accidentally share secrets:
``validate_production`` is called once at startup (see ``api/server.py``)
and refuses to boot if any production-unsafe default is still in place.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

_INSECURE_DEFAULTS = {
    "local-development-only-change-me",
    "change-me",
    "changeme",
    "secret",
    "password",
    "local-compose-jwt-secret-change-before-deploy",
    "local-compose-encryption-secret-change-before-deploy",
}


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        value.strip().rstrip("/")
        for value in os.environ.get(name, default).split(",")
        if value.strip()
    )


def _bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str = os.environ.get("JARVIS_ENV", "development").strip().lower()
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "sqlite:///./tmp/jarvis_web.db",
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "local-development-only-change-me")
    encryption_key: str = os.environ.get("JARVIS_ENCRYPTION_KEY", "")

    # A stolen access token is only useful for as long as it is valid, so the
    # default lifetime is kept short. Sessions are also revocable server-side
    # (see api/sessions.py), which further bounds the blast radius of a leak.
    access_token_minutes: int = int(os.environ.get("ACCESS_TOKEN_MINUTES", "60"))

    cors_origins: tuple[str, ...] = _csv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    chat_model: str = os.environ.get("JARVIS_CHAT_MODEL", "gemini-3.6-flash")
    auto_create_tables: bool = _bool("AUTO_CREATE_TABLES", "1")
    redis_required: bool = _bool("REDIS_REQUIRED", "0")

    # Cookie-based session transport (see api/security.py / api/server.py).
    # SameSite must be "none" (with Secure) when the web frontend and API are
    # deployed on different registrable domains; "lax" is fine for same-site
    # / local development setups.
    cookie_name: str = os.environ.get("SESSION_COOKIE_NAME", "jarvis_session")
    cookie_samesite: str = os.environ.get("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    cookie_domain: str = os.environ.get("SESSION_COOKIE_DOMAIN", "")

    # Retention window (days) for chat/task/cache/session history. See
    # scripts/retention_cleanup.py and the periodic task started in
    # api/server.py's lifespan.
    retention_days: int = int(os.environ.get("JARVIS_RETENTION_DAYS", "90"))

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        # Always secure in production. Allow explicit override for local
        # HTTPS dev setups via SESSION_COOKIE_SECURE=1.
        return self.is_production or _bool("SESSION_COOKIE_SECURE", "0")

    def validate_production(self) -> None:
        """Refuse to start with development-shaped configuration in
        production. Called once at API startup (see api/server.py)."""
        if not self.is_production:
            return

        problems: list[str] = []

        if self.jwt_secret in _INSECURE_DEFAULTS or len(self.jwt_secret) < 32:
            problems.append(
                "JWT_SECRET must be a random value with at least 32 characters in production"
            )

        if not self.encryption_key or self.encryption_key in _INSECURE_DEFAULTS:
            problems.append("JARVIS_ENCRYPTION_KEY must be configured in production")
        elif len(self.encryption_key) < 32:
            problems.append("JARVIS_ENCRYPTION_KEY must be at least 32 characters in production")
        elif not re.search(r"[A-Za-z]", self.encryption_key) or not re.search(r"[0-9]", self.encryption_key):
            problems.append(
                "JARVIS_ENCRYPTION_KEY looks weak (mix letters and numbers, ideally a "
                "generated random token, e.g. `openssl rand -base64 48`)"
            )

        if not self.database_url.startswith(("postgresql://", "postgres://", "postgresql+")):
            problems.append("Production DATABASE_URL must point to Postgres, not SQLite")

        if not self.redis_required:
            problems.append(
                "REDIS_REQUIRED must be enabled in production so rate limiting is enforced "
                "consistently across every API instance instead of silently falling back to "
                "an unshared in-memory counter"
            )

        if any(origin in {"*", "http://localhost:3000", "http://127.0.0.1:3000"} for origin in self.cors_origins):
            problems.append(
                "CORS_ORIGINS still contains a wildcard or a localhost development origin; "
                "set it to your exact production frontend origin(s)"
            )
        if not self.cors_origins:
            problems.append("CORS_ORIGINS must not be empty in production")

        if self.cookie_samesite not in {"lax", "strict", "none"}:
            problems.append("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            problems.append("SESSION_COOKIE_SAMESITE=none requires cookies to be Secure")

        if self.auto_create_tables:
            problems.append(
                "AUTO_CREATE_TABLES must be disabled in production; use Alembic migrations "
                "(`alembic upgrade head`) instead of implicit schema creation"
            )

        if problems:
            raise RuntimeError(
                "Refusing to start in production with unsafe configuration:\n- "
                + "\n- ".join(problems)
            )


settings = Settings()
