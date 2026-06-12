import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ChipItem, DccQuestion, MdpWord, ParolesTrack, ScoringConfig, Team
from app.schemas import (
    ChipsScoreRequest,
    ChipsStartRequest,
    ChipsSubmit,
    DccAnswerRequest,
    DccChooseRequest,
    DccQuestionCreate,
    MdpStartRound,
    ModuleStart,
    ParolesSubmit,
    PlacementSubmit,
    PiscineResult,
    ScoringUpdate,
    TeamUpdate,
)
from app.security import require_admin, require_team, team_uuid
from app.services import modules as mod
from app.services.game import build_game_state, ensure_session, get_scoring_map, update_ranks
from app.ws.manager import ws_manager

router = APIRouter(prefix="/game", tags=["game"])


async def _broadcast(db: AsyncSession) -> None:
    session = await ensure_session(db)
    state = await build_game_state(db)
    await ws_manager.broadcast(session.code, {"type": "state_update", "state": state})


@router.get("/state")
async def get_state(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await build_game_state(db)


@router.get("/public")
async def get_public_state(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    return await build_game_state(db)


# ─── Admin: teams & scoring ───────────────────────────────────────

@router.patch("/teams/{team_id}")
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    result = await db.execute(select(Team).where(Team.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(404, "Équipe introuvable")
    if body.name is not None:
        team.name = body.name
    if body.color is not None:
        team.color = body.color
    if body.member_count is not None:
        team.member_count = body.member_count
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.put("/scoring/{module}")
async def update_scoring(
    module: str,
    body: ScoringUpdate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    result = await db.execute(
        select(ScoringConfig).where(
            ScoringConfig.session_id == session.id, ScoringConfig.module == module
        )
    )
    row = result.scalar_one_or_none()
    if row:
        row.config = body.config
    else:
        db.add(ScoringConfig(session_id=session.id, module=module, config=body.config))
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.post("/reset")
async def reset_scores(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    for team in session.teams:
        team.score_total = 0
        team.rank = None
        team.eliminated = False
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.post("/module/start")
async def start_module(
    body: ModuleStart,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    if body.module == "dcc":
        data = await mod.dcc_start_question(db, session)
    elif body.module == "mdp":
        await mod.set_module_state(db, session, "mdp", (await mod.get_event_state(db, session)).state)
        data = {"started": True}
    elif body.module == "paroles":
        data = await mod.paroles_start(db, session)
    elif body.module == "poignards":
        data = await mod.poignards_display(db, session)
    else:
        await mod.set_module_state(db, session, body.module, (await mod.get_event_state(db, session)).state)
        data = {"module": body.module}
    await db.commit()
    await _broadcast(db)
    return data


# ─── DCC ──────────────────────────────────────────────────────────

@router.post("/dcc/start")
async def dcc_start(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.dcc_start_question(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/dcc/choose")
async def dcc_choose(
    body: DccChooseRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_team),
) -> dict:
    session = await ensure_session(db)
    try:
        data = await mod.dcc_team_choose(db, session, str(team_uuid(user)), body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    await _broadcast(db)
    return data


@router.get("/dcc/current")
async def dcc_current(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    return await mod.dcc_get_question_for_team(db, session, str(team_uuid(user)))


@router.post("/dcc/answer")
async def dcc_answer(
    body: DccAnswerRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_team),
) -> dict:
    session = await ensure_session(db)
    await mod.dcc_team_answer(db, session, str(team_uuid(user)), body.answer)
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.post("/dcc/reveal")
async def dcc_reveal(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.dcc_reveal_and_score(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/dcc/questions")
async def add_dcc_question(
    body: DccQuestionCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    q = DccQuestion(session_id=session.id, **body.model_dump())
    db.add(q)
    await db.commit()
    return {"id": str(q.id)}


@router.get("/dcc/questions")
async def list_dcc_questions(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> list:
    session = await ensure_session(db)
    result = await db.execute(select(DccQuestion).where(DccQuestion.session_id == session.id))
    return [
        {
            "id": str(q.id),
            "question": q.question,
            "category": q.category,
            "used": q.used,
        }
        for q in result.scalars()
    ]


# ─── MDP ──────────────────────────────────────────────────────────

@router.post("/mdp/start-turn")
async def mdp_start_turn(
    body: MdpStartRound,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.mdp_start_team_round(db, session, str(body.team_id), body.player_index)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/mdp/next-word")
async def mdp_next_word(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    es = await mod.get_event_state(db, session)
    current = es.state.get("mdp", {}).get("current", {})
    if str(team_uuid(user)) != current.get("team_id"):
        raise HTTPException(403, "Ce n'est pas votre tour")
    try:
        data = await mod.mdp_next_word(db, session)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/mdp/end-turn")
async def mdp_end_turn(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    try:
        data = await mod.mdp_end_turn(db, session)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    await _broadcast(db)
    return data


@router.get("/mdp/player-view")
async def mdp_player_view(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    es = await mod.get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current", {})
    tid = str(team_uuid(user))
    if current.get("team_id") != tid:
        return {"active": False, "word": None}
    return {
        "active": current.get("active", False),
        "word": current.get("word") if current.get("active") else None,
        "words_found": current.get("words_found", 0),
        "player_index": current.get("player_index"),
        "duration_sec": 30,
    }


@router.post("/mdp/finalize")
async def mdp_finalize(
    body: PlacementSubmit,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.mdp_finalize(db, session, body.placement)
    await db.commit()
    await _broadcast(db)
    return data


# ─── PAROLES ──────────────────────────────────────────────────────

@router.post("/paroles/start")
async def paroles_start(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.paroles_start(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/paroles/listen")
async def paroles_listen(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.paroles_listen(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/paroles/submit")
async def paroles_submit(
    body: ParolesSubmit,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_team),
) -> dict:
    session = await ensure_session(db)
    await mod.paroles_submit(db, session, str(team_uuid(user)), body.answers)
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.get("/paroles/view")
async def paroles_view(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    es = await mod.get_event_state(db, session)
    paroles = es.state.get("paroles", {})
    return {
        "phase": paroles.get("phase"),
        "title": paroles.get("title"),
        "display_text": paroles.get("display_text"),
        "blank_count": paroles.get("blank_count", 0),
        "listen_count": paroles.get("listen_count", 0),
        "locked": paroles.get("locked", {}).get(str(team_uuid(user)), False),
        "audio_url": paroles.get("audio_url"),
    }


@router.post("/paroles/score")
async def paroles_score(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.paroles_score(db, session)
    await db.commit()
    await _broadcast(db)
    return data


# ─── CHIPS ────────────────────────────────────────────────────────

@router.get("/chips")
async def list_chips(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> list:
    session = await ensure_session(db)
    result = await db.execute(select(ChipItem).where(ChipItem.session_id == session.id))
    return [{"id": str(c.id), "name": c.name, "flavors": c.flavors} for c in result.scalars()]


@router.post("/chips/start")
async def chips_start(
    body: ChipsStartRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.chips_start_round(db, session, body.chip_id, body.flavors_to_guess)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/chips/guess")
async def chips_guess(
    body: ChipsSubmit,
    db: AsyncSession = Depends(get_db),
    user=Depends(require_team),
) -> dict:
    session = await ensure_session(db)
    await mod.chips_submit_guesses(db, session, str(team_uuid(user)), body.guesses)
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.get("/chips/view")
async def chips_view(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    es = await mod.get_event_state(db, session)
    chips = es.state.get("chips", {})
    return {
        "phase": chips.get("phase"),
        "chip_name": chips.get("chip_name"),
        "flavors_to_guess_count": len(chips.get("flavors_to_guess", [])),
    }


@router.post("/chips/score")
async def chips_score(
    body: ChipsScoreRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.chips_score_team(
        db, session, str(body.team_id), body.correct_flavors, body.wrong_count
    )
    await db.commit()
    await _broadcast(db)
    return data


# ─── MOLKKY / PISCINE / POIGNARDS ─────────────────────────────────

@router.post("/molkky/result")
async def molkky_result(
    body: PlacementSubmit,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.molkky_submit(db, session, body.placement)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/piscine/result")
async def piscine_result(
    body: PiscineResult,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.piscine_submit(db, session, body.placement)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/poignards/start")
async def poignards_start(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.poignards_display(db, session)
    await db.commit()
    await _broadcast(db)
    return data
