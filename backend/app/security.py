from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import GameSession

ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


def create_token(data: dict[str, Any]) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if not creds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Non authentifié")
    try:
        return decode_token(creds.credentials)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide") from exc


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin requis")
    return user


async def require_team(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "team":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Équipe requise")
    return user


async def get_active_session(db: AsyncSession) -> GameSession:
    result = await db.execute(
        select(GameSession).where(GameSession.code == settings.session_code).limit(1)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session introuvable")
    return session


def team_uuid(user: dict) -> UUID:
    return UUID(user["team_id"])


def player_id(user: dict) -> str:
    return str(user.get("player_id") or user.get("sub") or "")
