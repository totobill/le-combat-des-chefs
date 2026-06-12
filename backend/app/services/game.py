import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import (
    ChipItem,
    DccQuestion,
    EventState,
    GameSession,
    MdpWord,
    ParolesTrack,
    ScoreEvent,
    ScoringConfig,
    SessionStatus,
    Team,
)
from app.services.defaults import (
    DEFAULT_CHIPS,
    DEFAULT_DCC_QUESTIONS,
    DEFAULT_MDP_WORDS,
    DEFAULT_PAROLES,
    DEFAULT_SCORING,
    DEFAULT_TEAMS,
    PROGRAM_MODULES,
)


async def ensure_session(db: AsyncSession) -> GameSession:
    result = await db.execute(
        select(GameSession)
        .where(GameSession.code == settings.session_code)
        .options(
            selectinload(GameSession.teams),
            selectinload(GameSession.scoring_configs),
            selectinload(GameSession.event_state),
        )
    )
    session = result.scalar_one_or_none()
    if session:
        return session

    session = GameSession(code=settings.session_code, status=SessionStatus.SETUP.value)
    db.add(session)
    await db.flush()

    for idx, t in enumerate(DEFAULT_TEAMS):
        db.add(
            Team(
                session_id=session.id,
                name=t["name"],
                color=t["color"],
                member_count=5,
            )
        )

    for module, cfg in DEFAULT_SCORING.items():
        db.add(ScoringConfig(session_id=session.id, module=module, config=cfg))

    db.add(EventState(session_id=session.id, module=None, state={"program": _default_program()}))

    for q in DEFAULT_DCC_QUESTIONS:
        db.add(DccQuestion(session_id=session.id, **q))

    for w in DEFAULT_MDP_WORDS:
        db.add(MdpWord(session_id=session.id, word=w))

    for p in DEFAULT_PAROLES:
        db.add(ParolesTrack(session_id=session.id, **p))

    for c in DEFAULT_CHIPS:
        db.add(ChipItem(session_id=session.id, **c))

    await db.commit()
    result = await db.execute(
        select(GameSession)
        .where(GameSession.id == session.id)
        .options(
            selectinload(GameSession.teams),
            selectinload(GameSession.scoring_configs),
            selectinload(GameSession.event_state),
        )
    )
    return result.scalar_one()


def _default_program() -> list[dict]:
    return [{**m, "status": "pending"} for m in PROGRAM_MODULES]


async def get_scoring_map(db: AsyncSession, session_id: uuid.UUID) -> dict[str, dict]:
    result = await db.execute(select(ScoringConfig).where(ScoringConfig.session_id == session_id))
    return {row.module: row.config for row in result.scalars()}


async def apply_placement_points(
    db: AsyncSession,
    session: GameSession,
    module: str,
    placement: dict[str, int],
) -> None:
    """placement: {team_id: rank} where rank is 1,2,3"""
    scoring = await get_scoring_map(db, session.id)
    cfg = scoring.get(module, {}).get("placement", {"1": 10, "2": 6, "3": 3})
    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = {str(t.id): t for t in teams_result.scalars()}
    points_awarded: dict[str, int] = {}
    for team_id, rank in placement.items():
        team = teams.get(team_id)
        if not team:
            continue
        pts = int(cfg.get(str(rank), 0))
        team.score_total += pts
        points_awarded[team_id] = pts
    db.add(
        ScoreEvent(
            session_id=session.id,
            module=module,
            payload={"placement": placement, "points_awarded": points_awarded},
        )
    )


async def update_ranks(db: AsyncSession, session_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Team).where(Team.session_id == session_id).order_by(Team.score_total.desc())
    )
    teams = list(result.scalars())
    for i, team in enumerate(teams):
        team.rank = i + 1


async def build_game_state(db: AsyncSession) -> dict[str, Any]:
    session = await ensure_session(db)
    scoring = await get_scoring_map(db, session.id)
    event_state = session.event_state.state if session.event_state else {}
    teams = sorted(session.teams, key=lambda t: t.score_total, reverse=True)
    return {
        "session": {
            "id": str(session.id),
            "code": session.code,
            "status": session.status,
            "current_module": session.current_module,
        },
        "teams": [
            {
                "id": str(t.id),
                "name": t.name,
                "color": t.color,
                "member_count": t.member_count,
                "score_total": t.score_total,
                "rank": t.rank,
                "eliminated": t.eliminated,
            }
            for t in teams
        ],
        "scoring": scoring,
        "event": {
            "module": session.event_state.module if session.event_state else None,
            "state": event_state,
        },
        "program": event_state.get("program", _default_program()),
    }
