"""TOTP-based two-factor authentication (RFC 6238).

The shared secret is stored in the existing encrypted UserSecret vault
(name "totp_secret" / "totp_secret_pending") — the same mechanism already
protecting the Gemini API key and GitHub token — rather than a new storage
path or a plaintext column.
"""

from __future__ import annotations

import pyotp


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str, issuer: str = "JARVIS") -> str:
    """A `otpauth://` URI suitable for rendering as a QR code in an
    authenticator app (Google Authenticator, 1Password, etc.)."""
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    try:
        return pyotp.totp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False
