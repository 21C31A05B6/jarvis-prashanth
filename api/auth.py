"""FastAPI authentication dependencies.

Tokens travel as an httpOnly cookie (set by /auth/signup and /auth/login) so
that JavaScript can never read the session token, even if an XSS bug slips
into the frontend. A ``Bearer`` header is still accepted for non-browser
clients (scripts, tests, mobile apps) that can't rely on cookies. Every
token is additionally checked against the sessions table so a logged-out or
revoked token stops working immediately, not just when it expires.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import User
from .security import decode_access_token
from .sessions import is_session_active


bearer = HTTPBearer(auto_error=False)


def _identity_for_token(token: str, db: Session) -> tuple[User, str]:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user_id = str(payload["sub"])
    jti = str(payload.get("jti", ""))
    if not is_session_active(db, jti, user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has ended")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return user, jti


def _token_from_request(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return request.cookies.get(settings.cookie_name, "")


def get_auth_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> tuple[User, str]:
    """Return (user, session_id) for the current request. Use this instead
    of ``get_current_user`` when the endpoint needs to know *which* session
    is active (logout, session management)."""
    token = _token_from_request(request, credentials)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return _identity_for_token(token, db)


def get_current_user(
    identity: tuple[User, str] = Depends(get_auth_context),
) -> User:
    return identity[0]


def websocket_user(websocket: WebSocket, db: Session) -> tuple[User, str]:
    """Resolve the authenticated user for a WebSocket connection.

    Deliberately does NOT accept a ``token`` query parameter: URLs are
    routinely captured in server/proxy access logs, browser history, and
    monitoring tools, which would leak the session token. The cookie set at
    login is sent automatically with the WS upgrade request; a Bearer
    Authorization header remains available for non-browser clients.
    """
    token = ""
    authorization = websocket.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        token = websocket.cookies.get(settings.cookie_name, "")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _identity_for_token(token, db)
