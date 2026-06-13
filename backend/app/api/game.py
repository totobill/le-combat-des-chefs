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
    MdpWordsCreate,
    ModuleStart,
    ParolesSubmit,
    PlacementSubmit,
    PiscineResult,
    ScoringUpdate,
    ScoreAdjust,
    BoardDisplay,
    TeamUpdate,
)
from app.security import require_admin, require_team, team_uuid
from app.services import modules as mod
from app.services.game import (
    RESETTABLE_MODULES,
    adjust_team_score,
    build_game_state,
    clear_board_display,
    ensure_session,
    get_scoring_map,
    reset_all_scores_and_progress,
    reset_module_progress,
    set_board_display,
    update_ranks,
)
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
    if body.score_total is not None:
        team.score_total = max(0, body.score_total)
        await update_ranks(db, team.session_id)
    await db.commit()
    await _broadcast(db)
    return {"ok": True, "score_total": team.score_total}


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


@router.post("/scores/adjust")
async def adjust_score(
    body: ScoreAdjust,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    try:
        team = await adjust_team_score(db, session, str(body.team_id), body.delta)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    await _broadcast(db)
    return {"ok": True, "score_total": team.score_total}


@router.post("/board/display")
async def board_display(
    body: BoardDisplay,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await set_board_display(db, session, body.model_dump())
    await db.commit()
    await _broadcast(db)
    return data


@router.delete("/board/display")
async def board_display_clear(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    await clear_board_display(db, session)
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.post("/reset")
async def reset_scores(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    await reset_all_scores_and_progress(db, session)
    await db.commit()
    await _broadcast(db)
    return {"ok": True}


@router.post("/reset/{module}")
async def reset_module(
    module: str,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    if module not in RESETTABLE_MODULES:
        raise HTTPException(400, f"Module inconnu : {module}")
    session = await ensure_session(db)
    try:
        await reset_module_progress(db, session, module)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await db.commit()
    await _broadcast(db)
    return {"ok": True, "module": module}


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


@router.post("/dcc/finalize")
async def dcc_finalize(
    body: PlacementSubmit,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.dcc_finalize(db, session, body.placement)
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


@router.delete("/dcc/questions/{question_id}")
async def delete_dcc_question(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == question_id))
    q = result.scalar_one_or_none()
    if not q:
        raise HTTPException(404, "Question introuvable")
    await db.delete(q)
    await db.commit()
    return {"ok": True}


@router.get("/dcc/questions")
async def list_dcc_questions(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> list:
    session = await ensure_session(db)
    result = await db.execute(select(DccQuestion).where(DccQuestion.session_id == session.id))
    return [
        {
            "id": str(q.id),
            "question": q.question,
            "category": q.category,
            "duo_opts": q.duo_opts,
            "duo_correct": q.duo_correct,
            "carre_opts": q.carre_opts,
            "carre_correct": q.carre_correct,
            "cash_answer": q.cash_answer,
            "cash_aliases": q.cash_aliases or [],
            "used": q.used,
        }
        for q in result.scalars()
    ]


# ─── MDP ──────────────────────────────────────────────────────────

@router.get("/mdp/words")
async def list_mdp_words(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> list:
    session = await ensure_session(db)
    result = await db.execute(select(MdpWord).where(MdpWord.session_id == session.id))
    return [
        {"id": str(w.id), "word": w.word, "used": w.used}
        for w in result.scalars()
    ]


@router.post("/mdp/words")
async def add_mdp_words(
    body: MdpWordsCreate,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    added: list[str] = []
    for raw in body.words:
        word = raw.strip()
        if not word:
            continue
        db.add(MdpWord(session_id=session.id, word=word))
        added.append(word)
    if not added:
        raise HTTPException(400, "Aucun mot valide")
    await db.commit()
    return {"ok": True, "count": len(added), "words": added}


@router.delete("/mdp/words/{word_id}")
async def delete_mdp_word(
    word_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    result = await db.execute(select(MdpWord).where(MdpWord.id == word_id))
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Mot introuvable")
    await db.delete(w)
    await db.commit()
    return {"ok": True}


@router.post("/mdp/start-turn")
async def mdp_start_turn(
    body: MdpStartRound,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    try:
        data = await mod.mdp_start_team_round(db, session, str(body.team_id), body.player_index)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
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
async def mdp_end_turn(
    db: AsyncSession = Depends(get_db),
    user=Depends(require_team),
) -> dict:
    session = await ensure_session(db)
    es = await mod.get_event_state(db, session)
    current = es.state.get("mdp", {}).get("current", {})
    if current.get("team_id") != str(team_uuid(user)):
        raise HTTPException(403, "Ce n'est pas votre passage")
    data = await mod.mdp_end_turn(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.post("/mdp/end-turn/force")
async def mdp_end_turn_force(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.mdp_end_turn(db, session)
    await db.commit()
    await _broadcast(db)
    return data


@router.get("/mdp/player-view")
async def mdp_player_view(db: AsyncSession = Depends(get_db), user=Depends(require_team)) -> dict:
    session = await ensure_session(db)
    data = await mod.mdp_player_view(db, session, str(team_uuid(user)))
    await db.commit()
    return data


@router.get("/mdp/host-view")
async def mdp_host_view(db: AsyncSession = Depends(get_db), _=Depends(require_admin)) -> dict:
    session = await ensure_session(db)
    data = await mod.mdp_host_view(db, session)
    await db.commit()
    return data


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


@router.post("/chips/finalize")
async def chips_finalize(
    body: PlacementSubmit,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
) -> dict:
    session = await ensure_session(db)
    data = await mod.chips_finalize(db, session, body.placement)
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
