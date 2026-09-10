"""Server-side session/device management backing JWT revocation.

Access tokens are short-lived, signed JWTs (see api/security.py), but a
stateless JWT can't be revoked before it expires. Every issued token is
mirrored here as a Session row keyed by the token's ``jti``; auth checks
consult this table so that logout, "log out everywhere", and revoking a
single device all take effect immediately instead of waiting out the token's
remaining lifetime.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as OrmSession

from .database import SessionLocal
from .models import Session as SessionRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    """SQLite silently drops tzinfo on DateTime(timezone=True) columns
    (Postgres does not), so a value read back can be naive even though it
    was stored as UTC. Normalize before comparing to an aware "now"."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def create_session(
    db: OrmSession,
    *,
    jti: str,
    user_id: str,
    expires_at: datetime,
    user_agent: str = "",
    ip_address: str = "",
) -> None:
    db.add(SessionRow(
        id=jti,
        user_id=user_id,
        expires_at=expires_at,
        last_seen_at=_now(),
        user_agent=user_agent[:300],
        ip_address=ip_address[:64],
    ))
    db.commit()


def is_session_active(db: OrmSession, jti: str, user_id: str) -> bool:
    row = db.scalar(select(SessionRow).where(
        SessionRow.id == jti,
        SessionRow.user_id == user_id,
    ))
    if row is None:
        return False
    if row.revoked_at is not None:
        return False
    if _aware(row.expires_at) <= _now():
        return False
    row.last_seen_at = _now()
    db.commit()
    return True


def revoke_session(db: OrmSession, user_id: str, session_id: str) -> bool:
    result = db.execute(
        update(SessionRow)
        .where(SessionRow.id == session_id, SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    db.commit()
    return result.rowcount > 0


def revoke_all_sessions(db: OrmSession, user_id: str, *, except_id: str | None = None) -> int:
    query = update(SessionRow).where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None))
    if except_id:
        query = query.where(SessionRow.id != except_id)
    result = db.execute(query.values(revoked_at=_now()))
    db.commit()
    return result.rowcount


def list_sessions(db: OrmSession, user_id: str) -> list[SessionRow]:
    return list(db.scalars(
        select(SessionRow)
        .where(SessionRow.user_id == user_id, SessionRow.revoked_at.is_(None), SessionRow.expires_at > _now())
        .order_by(SessionRow.last_seen_at.desc())
    ).all())


def purge_expired_sessions(retention_days: int = 30) -> int:
    """Delete session rows that expired (or were revoked) more than
    ``retention_days`` ago. Called by the periodic retention job (bug #24)
    so the sessions table doesn't grow without bound."""
    cutoff = _now() - timedelta(days=retention_days)
    with SessionLocal.begin() as db:
        result = db.execute(delete(SessionRow).where(SessionRow.expires_at < cutoff))
        return result.rowcount
