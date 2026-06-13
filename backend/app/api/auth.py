from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.config import settings
from app.database import get_db
from app.models import Team
from app.schemas import AdminLoginRequest, JoinRequest, TokenResponse
from app.security import create_token
from app.services.game import ensure_session
from sqlalchemy import select

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/admin", response_model=TokenResponse)
async def admin_login(body: AdminLoginRequest) -> TokenResponse:
    if body.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    token = create_token({"role": "admin", "sub": "admin"})
    return TokenResponse(access_token=token, role="admin")


@router.post("/join", response_model=TokenResponse)
async def join_team(body: JoinRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    if body.session_code != settings.session_code:
        raise HTTPException(status_code=400, detail="Code session invalide")
    session = await ensure_session(db)
    result = await db.execute(select(Team).where(Team.id == body.team_id, Team.session_id == session.id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe introuvable")
    player_id = str(uuid.uuid4())
    token = create_token(
        {
            "role": "team",
            "sub": str(team.id),
            "team_id": str(team.id),
            "display_name": body.display_name,
            "player_id": player_id,
        }
    )
    return TokenResponse(
        access_token=token,
        role="team",
        team_id=str(team.id),
        display_name=body.display_name,
        player_id=player_id,
    )
