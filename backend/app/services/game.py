import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
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


RESETTABLE_MODULES = frozenset(
    {"mdp", "dcc", "chips", "molkky", "paroles", "piscine", "poignards"}
)


def record_module_points(state: dict, module: str, team_id: str, points: int) -> None:
    if points <= 0:
        return
    ledger = state.setdefault("module_points", {})
    mod = ledger.setdefault(module, {})
    mod[team_id] = mod.get(team_id, 0) + points


def get_module_points(state: dict, module: str) -> dict[str, int]:
    return dict(state.get("module_points", {}).get(module, {}))


async def _backfill_module_points(
    db: AsyncSession, session: GameSession, module: str, state: dict
) -> dict[str, int]:
    """Sessions sans registre : estimation depuis l'état et les événements."""
    totals: dict[str, int] = defaultdict(int)
    mod_state = state.get(module, {})

    if module == "mdp":
        for tid, turns in mod_state.get("team_scores", {}).items():
            for turn in turns:
                totals[tid] += int(turn.get("points", 0))
    elif module == "dcc":
        for tid, result in mod_state.get("results", {}).items():
            totals[tid] += int(result.get("points", 0))
    elif module == "chips":
        for tid, result in mod_state.get("results", {}).items():
            totals[tid] += int(result.get("points", 0))
    elif module == "paroles":
        for tid, result in mod_state.get("results", {}).items():
            totals[tid] += int(result.get("score", 0))

    events = await db.execute(
        select(ScoreEvent).where(
            ScoreEvent.session_id == session.id, ScoreEvent.module == module
        )
    )
    for ev in events.scalars():
        for tid, pts in ev.payload.get("points_awarded", {}).items():
            totals[tid] += int(pts)

    return dict(totals)


async def _reset_module_content(db: AsyncSession, session: GameSession, module: str) -> None:
    if module == "dcc":
        for q in (
            await db.execute(select(DccQuestion).where(DccQuestion.session_id == session.id))
        ).scalars():
            q.used = False
    elif module == "mdp":
        for w in (
            await db.execute(select(MdpWord).where(MdpWord.session_id == session.id))
        ).scalars():
            w.used = False
    elif module == "paroles":
        for t in (
            await db.execute(select(ParolesTrack).where(ParolesTrack.session_id == session.id))
        ).scalars():
            t.used = False


async def reset_module_progress(db: AsyncSession, session: GameSession, module: str) -> None:
    if module not in RESETTABLE_MODULES:
        raise ValueError(f"Module inconnu : {module}")

    es = session.event_state
    if not es:
        raise ValueError("État de session introuvable")

    state = dict(es.state or {})
    totals = get_module_points(state, module)
    if not totals:
        totals = await _backfill_module_points(db, session, module, state)

    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = {str(t.id): t for t in teams_result.scalars()}
    for team_id, pts in totals.items():
        team = teams.get(team_id)
        if team:
            team.score_total = max(0, team.score_total - pts)

    state.get("module_points", {}).pop(module, None)
    state.pop(module, None)

    program = state.get("program", _default_program())
    for item in program:
        if item.get("id") == module:
            item["status"] = "pending"
    state["program"] = program

    if es.module == module:
        es.module = None
    if session.current_module == module:
        session.current_module = None

    es.state = state

    await db.execute(
        delete(ScoreEvent).where(
            ScoreEvent.session_id == session.id, ScoreEvent.module == module
        )
    )
    await _reset_module_content(db, session, module)
    await update_ranks(db, session.id)


async def reset_all_scores_and_progress(db: AsyncSession, session: GameSession) -> None:
    for team in session.teams:
        team.score_total = 0
        team.rank = None
        team.eliminated = False

    await db.execute(delete(ScoreEvent).where(ScoreEvent.session_id == session.id))

    es = session.event_state
    if es:
        program = (es.state or {}).get("program", _default_program())
        es.state = {"program": [{**item, "status": "pending"} for item in program]}
        es.module = None

    session.current_module = None

    for module in RESETTABLE_MODULES:
        await _reset_module_content(db, session, module)

    await update_ranks(db, session.id)


async def adjust_team_score(
    db: AsyncSession, session: GameSession, team_id: str, delta: int
) -> Team:
    result = await db.execute(
        select(Team).where(Team.id == uuid.UUID(team_id), Team.session_id == session.id)
    )
    team = result.scalar_one_or_none()
    if not team:
        raise ValueError("Équipe introuvable")
    team.score_total = max(0, team.score_total + delta)
    es = session.event_state
    if es:
        record_module_points(es.state, "manual", team_id, max(0, delta))
    await update_ranks(db, session.id)
    return team


async def set_board_display(db: AsyncSession, session: GameSession, display: dict) -> dict:
    es = session.event_state
    if not es:
        raise ValueError("État de session introuvable")
    es.state = {**es.state, "board": display}
    return display


async def clear_board_display(db: AsyncSession, session: GameSession) -> None:
    es = session.event_state
    if es and "board" in es.state:
        state = dict(es.state)
        state.pop("board", None)
        es.state = state


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
    es = session.event_state
    event_state = es.state if es else {}

    for team_id, rank in placement.items():
        team = teams.get(team_id)
        if not team:
            continue
        pts = int(cfg.get(str(rank), 0))
        team.score_total += pts
        points_awarded[team_id] = pts
        record_module_points(event_state, module, team_id, pts)

    if es:
        es.state = event_state

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
