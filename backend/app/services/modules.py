import copy
import random
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import ChipItem, DccQuestion, EventState, GameSession, MdpWord, ParolesTrack, Team
from app.services.game import (
    apply_placement_points,
    get_scoring_map,
    record_module_points,
    update_ranks,
)


async def get_event_state(db: AsyncSession, session: GameSession) -> EventState:
    result = await db.execute(select(EventState).where(EventState.session_id == session.id))
    es = result.scalar_one()
    return es


async def set_module_state(
    db: AsyncSession, session: GameSession, module: str | None, state: dict[str, Any]
) -> EventState:
    es = await get_event_state(db, session)
    es.module = module
    es.state = state
    session.current_module = module
    return es


# ─── DCC ───────────────────────────────────────────────────────────

def _dcc_team_entry(dcc: dict, team_id: str) -> dict:
    teams = dcc.setdefault("teams", {})
    if team_id not in teams:
        teams[team_id] = {"status": "choosing"}
    return teams[team_id]


def _save_dcc_state(es: EventState, dcc: dict) -> None:
    """Persist nested DCC updates (JSONB requires a fresh dict + flag_modified)."""
    state = copy.deepcopy(es.state or {})
    state["dcc"] = copy.deepcopy(dcc)
    es.state = state
    flag_modified(es, "state")


async def _load_dcc_question(db: AsyncSession, session: GameSession, question_id: str | None) -> DccQuestion:
    if question_id:
        result = await db.execute(
            select(DccQuestion).where(
                DccQuestion.id == uuid.UUID(question_id),
                DccQuestion.session_id == session.id,
            )
        )
        question = result.scalar_one_or_none()
        if not question:
            raise ValueError("Question introuvable")
        return question

    result = await db.execute(
        select(DccQuestion)
        .where(DccQuestion.session_id == session.id, DccQuestion.used.is_(False))
        .limit(50)
    )
    pool = list(result.scalars())
    if not pool:
        result = await db.execute(select(DccQuestion).where(DccQuestion.session_id == session.id))
        for q in result.scalars():
            q.used = False
        pool = list(
            (await db.execute(select(DccQuestion).where(DccQuestion.session_id == session.id))).scalars()
        )
    if not pool:
        raise ValueError("Aucune question disponible")
    return random.choice(pool)


async def _dcc_all_question_ids(
    db: AsyncSession, session: GameSession, question_ids: list[str] | None = None
) -> list[str]:
    if question_ids:
        return question_ids
    result = await db.execute(
        select(DccQuestion)
        .where(DccQuestion.session_id == session.id)
        .order_by(DccQuestion.category, DccQuestion.question)
    )
    questions = list(result.scalars())
    if not questions:
        raise ValueError("Aucune question dans la banque")
    return [str(q.id) for q in questions]


def _dcc_ensure_episode(dcc: dict) -> None:
    if dcc.get("episode_question_ids"):
        return
    if dcc.get("question_id"):
        dcc["episode_question_ids"] = [dcc["question_id"]]
    dcc.setdefault("team_progress", {})


def _dcc_team_progress(dcc: dict, team_id: str) -> dict:
    _dcc_ensure_episode(dcc)
    progress = dcc.setdefault("team_progress", {})
    if team_id not in progress:
        progress[team_id] = {"index": 0, "finished": False}
    return progress[team_id]


async def _dcc_init_team_progress(db: AsyncSession, session: GameSession, dcc: dict) -> None:
    result = await db.execute(select(Team).where(Team.session_id == session.id))
    progress: dict[str, dict] = {}
    existing = dcc.get("team_progress") or {}
    for team in result.scalars():
        tid = str(team.id)
        progress[tid] = existing.get(tid) or {"index": 0, "finished": False}
    dcc["team_progress"] = progress


async def _dcc_load_question_at_index(
    db: AsyncSession, session: GameSession, es: EventState, dcc: dict, team_id: str
) -> DccQuestion | None:
    _dcc_ensure_episode(dcc)
    prog = _dcc_team_progress(dcc, team_id)
    qids = dcc.get("episode_question_ids") or []
    total = len(qids)

    if prog.get("finished") or not qids:
        dcc["active_team_id"] = team_id
        dcc.pop("question_id", None)
        dcc.pop("question", None)
        dcc.pop("category", None)
        dcc["round"] = total
        dcc["total"] = total
        _save_dcc_state(es, dcc)
        return None

    idx = int(prog.get("index", 0))
    if idx >= total:
        prog["finished"] = True
        dcc["active_team_id"] = team_id
        dcc.pop("question_id", None)
        dcc.pop("question", None)
        dcc.pop("category", None)
        dcc["round"] = total
        dcc["total"] = total
        _save_dcc_state(es, dcc)
        return None

    qid = qids[idx]
    question = await _load_dcc_question(db, session, qid)
    dcc["question_id"] = qid
    dcc["question"] = question.question
    dcc["category"] = question.category
    dcc["round"] = idx + 1
    dcc["total"] = total
    dcc["active_team_id"] = team_id

    entry = dcc.get("teams", {}).get(team_id)
    if not entry or entry.get("question_id") != qid:
        dcc.setdefault("teams", {})[team_id] = {"status": "choosing", "question_id": qid}

    _save_dcc_state(es, dcc)
    return question


async def _dcc_assert_active_team(dcc: dict, team_id: str) -> None:
    active = dcc.get("active_team_id")
    if not active:
        raise ValueError("L'animateur n'a pas encore désigné l'équipe au passage")
    if team_id != active:
        raise ValueError("Ce n'est pas votre tour")


async def dcc_start_episode(
    db: AsyncSession,
    session: GameSession,
    team_id: str,
    question_ids: list[str] | None = None,
) -> dict:
    es = await get_event_state(db, session)
    qids = await _dcc_all_question_ids(db, session, question_ids)
    previous = es.state.get("dcc", {})

    dcc: dict[str, Any] = {
        "phase": "active",
        "episode_question_ids": qids,
        "teams": {},
        "results": previous.get("results", {}),
        "revealed": False,
    }
    if previous.get("episode_question_ids") == qids and previous.get("team_progress"):
        dcc["team_progress"] = copy.deepcopy(previous["team_progress"])
    else:
        await _dcc_init_team_progress(db, session, dcc)

    es.state = {**es.state, "dcc": dcc}
    await _dcc_load_question_at_index(db, session, es, es.state["dcc"], team_id)
    await set_module_state(db, session, "dcc", es.state)
    return es.state["dcc"]


async def dcc_start_question(
    db: AsyncSession, session: GameSession, question_id: str | None = None, team_id: str | None = None
) -> dict:
    if not team_id:
        raise ValueError("Choisissez l'équipe au passage")
    qids = [question_id] if question_id else None
    return await dcc_start_episode(db, session, team_id, qids)


async def dcc_advance_question(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        raise ValueError("Aucune épreuve en cours")

    team_id = dcc.get("active_team_id")
    if not team_id:
        raise ValueError("Aucune équipe active")

    entry = dcc.get("teams", {}).get(team_id, {})
    if entry.get("status") != "done":
        raise ValueError("La question en cours n'est pas terminée pour cette équipe")

    prog = _dcc_team_progress(dcc, team_id)
    prog["index"] = int(prog.get("index", 0)) + 1
    await _dcc_load_question_at_index(db, session, es, dcc, team_id)
    return es.state.get("dcc", dcc)


async def dcc_set_active_team(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        raise ValueError("Aucune épreuve en cours")

    team_result = await db.execute(
        select(Team).where(Team.id == uuid.UUID(team_id), Team.session_id == session.id)
    )
    if not team_result.scalar_one_or_none():
        raise ValueError("Équipe introuvable")

    await _dcc_load_question_at_index(db, session, es, dcc, team_id)
    return es.state.get("dcc", dcc)


async def dcc_team_choose(db: AsyncSession, session: GameSession, team_id: str, mode: str) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        raise ValueError("Aucune question en cours")
    await _dcc_assert_active_team(dcc, team_id)
    if mode not in ("duo", "carre", "cash"):
        raise ValueError("Mode invalide")
    entry = _dcc_team_entry(dcc, team_id)
    if entry.get("status") == "done":
        raise ValueError("Question déjà terminée pour votre équipe")
    entry["mode"] = mode
    entry["status"] = "answering"
    _save_dcc_state(es, dcc)
    return dcc


async def _score_dcc_team(
    db: AsyncSession,
    session: GameSession,
    es: EventState,
    dcc: dict,
    team_id: str,
    question: DccQuestion,
    mode: str,
    answer: Any,
) -> dict[str, Any]:
    scoring = await get_scoring_map(db, session.id)
    pts_map = scoring.get("dcc", {"duo": 1, "carre": 3, "cash": 6})
    correct = False
    if mode == "duo":
        correct = answer == question.duo_correct
        pts = pts_map.get("duo", 1)
    elif mode == "carre":
        correct = answer == question.carre_correct
        pts = pts_map.get("carre", 3)
    else:
        ans_str = str(answer or "").strip().lower()
        correct_answers = [question.cash_answer.lower()] + [
            a.lower() for a in (question.cash_aliases or [])
        ]
        correct = ans_str in correct_answers
        pts = pts_map.get("cash", 6)
    earned = pts if correct else 0

    result = {
        "mode": mode,
        "correct": correct,
        "points": earned,
        "correct_answer": {
            "duo": question.duo_opts[question.duo_correct],
            "carre": question.carre_opts[question.carre_correct],
            "cash": question.cash_answer,
        },
    }

    team_result = await db.execute(
        select(Team).where(Team.id == uuid.UUID(team_id), Team.session_id == session.id)
    )
    team = team_result.scalar_one_or_none()
    if team and earned > 0:
        team.score_total += earned
        record_module_points(es.state, "dcc", team_id, earned)

    qid = str(question.id)
    dcc.setdefault("results", {}).setdefault(team_id, {})[qid] = result
    entry = _dcc_team_entry(dcc, team_id)
    entry["status"] = "done"
    entry["result"] = result
    entry["question_id"] = qid
    await update_ranks(db, session.id)
    return result


async def dcc_team_answer(db: AsyncSession, session: GameSession, team_id: str, answer: Any) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        raise ValueError("Aucune question en cours")
    await _dcc_assert_active_team(dcc, team_id)
    entry = _dcc_team_entry(dcc, team_id)
    mode = entry.get("mode")
    if entry.get("status") != "answering" or not mode:
        raise ValueError("Choisissez d'abord Duo, Carré ou Cash")
    if "answer" in entry and entry.get("status") != "answering":
        raise ValueError("Réponse déjà envoyée")

    qid = uuid.UUID(dcc["question_id"])
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
    question = result.scalar_one()
    entry["answer"] = answer

    if mode in ("duo", "carre"):
        scored = await _score_dcc_team(db, session, es, dcc, team_id, question, mode, answer)
        _save_dcc_state(es, dcc)
        return {"status": "done", "result": scored}

    entry["status"] = "pending"
    _save_dcc_state(es, dcc)
    return {"status": "pending"}


async def dcc_validate_cash(
    db: AsyncSession, session: GameSession, team_id: str, correct: bool
) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    entry = _dcc_team_entry(dcc, team_id)
    if entry.get("mode") != "cash" or entry.get("status") != "pending":
        raise ValueError("Pas de réponse Cash en attente")

    qid = uuid.UUID(dcc["question_id"])
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
    question = result.scalar_one()
    answer = entry.get("answer", "")
    if not correct:
        scored = {
            "mode": "cash",
            "correct": False,
            "points": 0,
            "correct_answer": {
                "duo": question.duo_opts[question.duo_correct],
                "carre": question.carre_opts[question.carre_correct],
                "cash": question.cash_answer,
            },
        }
        entry["status"] = "done"
        entry["result"] = scored
        dcc.setdefault("results", {})[team_id] = scored
    else:
        scored = await _score_dcc_team(db, session, es, dcc, team_id, question, "cash", answer)
        entry["result"] = scored

    _save_dcc_state(es, dcc)
    return dcc


async def dcc_get_question_for_team(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        return {"active": False, "status": "idle"}

    active_team_id = dcc.get("active_team_id")
    if not active_team_id:
        return {
            "active": False,
            "status": "waiting_host",
            "question": dcc.get("question"),
            "category": dcc.get("category"),
            "message": "L'animateur prépare le passage…",
        }
    if team_id != active_team_id:
        teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
        teams = {str(t.id): t for t in teams_result.scalars()}
        active_team = teams.get(active_team_id)
        prog = _dcc_team_progress(dcc, team_id)
        return {
            "active": False,
            "status": "waiting",
            "question": dcc.get("question"),
            "category": dcc.get("category"),
            "round": dcc.get("round"),
            "total": dcc.get("total"),
            "active_team_name": active_team.name if active_team else "Une autre équipe",
            "message": f"C'est au tour de {active_team.name if active_team else 'une autre équipe'}.",
            "team_question_index": prog.get("index", 0),
        }

    prog = _dcc_team_progress(dcc, team_id)
    if prog.get("finished") or not dcc.get("question_id"):
        return {
            "active": False,
            "status": "team_finished",
            "message": "Votre équipe a terminé toutes les questions de l'épreuve.",
            "round": dcc.get("total"),
            "total": dcc.get("total"),
        }

    qid = uuid.UUID(dcc["question_id"])
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
    question = result.scalar_one()
    entry = dcc.get("teams", {}).get(team_id, {"status": "choosing"})
    mode = entry.get("mode")
    status = entry.get("status", "choosing")
    opts = None
    if mode == "duo":
        opts = question.duo_opts
    elif mode == "carre":
        opts = question.carre_opts

    payload: dict[str, Any] = {
        "active": True,
        "phase": "active",
        "question_id": dcc.get("question_id"),
        "question": dcc.get("question"),
        "category": dcc.get("category"),
        "mode": mode,
        "options": opts,
        "status": status,
        "result": entry.get("result"),
        "round": dcc.get("round"),
        "total": dcc.get("total"),
    }
    if status == "pending":
        payload["submitted_answer"] = entry.get("answer")
    return payload


async def dcc_host_view(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "active":
        return {"active": False}

    _dcc_ensure_episode(dcc)
    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = {str(t.id): t for t in teams_result.scalars()}
    active_team_id = dcc.get("active_team_id")
    active_team = teams.get(active_team_id) if active_team_id else None
    episode_total = len(dcc.get("episode_question_ids") or [])

    question = None
    answers = None
    if dcc.get("question_id"):
        qid = uuid.UUID(dcc["question_id"])
        result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
        question = result.scalar_one()
        answers = {
            "duo": question.duo_opts[question.duo_correct],
            "carre": question.carre_opts[question.carre_correct],
            "cash": question.cash_answer,
        }

    team_status = []
    for tid, team in teams.items():
        prog = _dcc_team_progress(dcc, tid)
        idx = int(prog.get("index", 0))
        finished = bool(prog.get("finished"))
        entry = dcc.get("teams", {}).get(tid) if tid == active_team_id else None
        if finished:
            status = "finished"
        elif tid == active_team_id and entry:
            status = entry.get("status", "choosing")
        elif tid == active_team_id:
            status = "choosing"
        else:
            status = "waiting"
        team_status.append(
            {
                "team_id": tid,
                "team_name": team.name,
                "team_color": team.color,
                "status": status,
                "is_active": tid == active_team_id,
                "question_index": idx,
                "question_total": episode_total,
                "finished": finished,
            }
        )

    pending = []
    for team_id, entry in dcc.get("teams", {}).items():
        if entry.get("mode") == "cash" and entry.get("status") == "pending":
            team = teams.get(team_id)
            pending.append(
                {
                    "team_id": team_id,
                    "team_name": team.name if team else team_id,
                    "team_color": team.color if team else "#888",
                    "answer": entry.get("answer", ""),
                }
            )

    active_entry = dcc.get("teams", {}).get(active_team_id or "", {}) if active_team_id else {}
    can_advance = (
        bool(active_team_id)
        and active_entry.get("status") == "done"
        and not _dcc_team_progress(dcc, active_team_id).get("finished")
    )

    return {
        "active": True,
        "question_id": dcc.get("question_id"),
        "question": dcc.get("question"),
        "category": dcc.get("category"),
        "round": dcc.get("round"),
        "total": dcc.get("total"),
        "episode_total": episode_total,
        "active_team_id": active_team_id,
        "active_team_name": active_team.name if active_team else None,
        "active_team_color": active_team.color if active_team else None,
        "active_team_finished": bool(
            active_team_id and _dcc_team_progress(dcc, active_team_id).get("finished")
        ),
        "can_advance": can_advance,
        "team_status": team_status,
        "answers": answers,
        "pending_cash": pending,
    }


async def dcc_reveal_and_score(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    qid = uuid.UUID(dcc["question_id"])
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
    question = result.scalar_one()
    scoring = await get_scoring_map(db, session.id)
    pts_map = scoring.get("dcc", {"duo": 1, "carre": 3, "cash": 6})
    results: dict[str, Any] = {}
    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = {str(t.id): t for t in teams_result.scalars()}

    for team_id, mode in dcc.get("team_choices", {}).items():
        answer = dcc.get("team_answers", {}).get(team_id)
        correct = False
        if mode == "duo":
            correct = answer == question.duo_correct
            pts = pts_map.get("duo", 1)
        elif mode == "carre":
            correct = answer == question.carre_correct
            pts = pts_map.get("carre", 3)
        else:
            ans_str = str(answer or "").strip().lower()
            correct_answers = [question.cash_answer.lower()] + [
                a.lower() for a in (question.cash_aliases or [])
            ]
            correct = ans_str in correct_answers
            pts = pts_map.get("cash", 6)
        earned = pts if correct else 0
        if team_id in teams:
            teams[team_id].score_total += earned
            record_module_points(es.state, "dcc", team_id, earned)
        results[team_id] = {
            "mode": mode,
            "correct": correct,
            "points": earned,
            "correct_answer": {
                "duo": question.duo_opts[question.duo_correct],
                "carre": question.carre_opts[question.carre_correct],
                "cash": question.cash_answer,
            },
        }

    dcc["revealed"] = True
    dcc["phase"] = "done"
    dcc["results"] = results
    dcc["correct"] = {
        "duo": question.duo_correct,
        "carre": question.carre_correct,
        "cash": question.cash_answer,
        "duo_opts": question.duo_opts,
        "carre_opts": question.carre_opts,
    }
    _save_dcc_state(es, dcc)
    await update_ranks(db, session.id)
    return dcc


async def dcc_finalize(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "dcc", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    dcc["finalized"] = True
    dcc["episode_placement"] = placement
    _save_dcc_state(es, dcc)
    return dcc


# ─── MDP ───────────────────────────────────────────────────────────

MDP_COUNTDOWN_SEC = 5
MDP_TURN_SEC = 30


def _mdp_norm_team_id(team_id: str) -> str:
    return str(uuid.UUID(team_id))


def _mdp_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _mdp_elapsed_sec(since_iso: str) -> float:
    from datetime import UTC, datetime

    started_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
    return (datetime.now(UTC) - started_dt).total_seconds()


def _mdp_countdown_remaining(started_at: str | None) -> int:
    if not started_at:
        return MDP_COUNTDOWN_SEC
    return max(0, MDP_COUNTDOWN_SEC - int(_mdp_elapsed_sec(started_at)))


def _mdp_turn_duration(scoring_mdp: dict | None = None) -> int:
    if scoring_mdp:
        raw = scoring_mdp.get("turn_sec")
        if raw is not None:
            return max(1, int(raw))
    return MDP_TURN_SEC


def _mdp_turn_remaining(turn_started_at: str | None, duration: int | None = None) -> int:
    dur = duration if duration is not None else MDP_TURN_SEC
    if not turn_started_at:
        return dur
    return max(0, dur - int(_mdp_elapsed_sec(turn_started_at)))


def _mdp_playing_timer_fields(current: dict, scoring_mdp: dict | None = None) -> dict[str, Any]:
    duration = _mdp_turn_duration(scoring_mdp)
    remaining = _mdp_turn_remaining(current.get("turn_started_at"), duration)
    return {
        "remaining_sec": remaining,
        "turn_duration_sec": duration,
        "timer_running": remaining > 0,
    }


def _mdp_is_active(mdp: dict) -> bool:
    current = mdp.get("current")
    return bool(current and current.get("phase") in ("countdown", "playing"))


def _save_mdp_state(es: EventState, mdp: dict) -> None:
    state = copy.deepcopy(es.state or {})
    state["mdp"] = copy.deepcopy(mdp)
    es.state = state
    flag_modified(es, "state")


async def _mdp_pick_word(db: AsyncSession, session: GameSession, exclude_id: str | None = None) -> MdpWord:
    result = await db.execute(
        select(MdpWord).where(MdpWord.session_id == session.id, MdpWord.used.is_(False))
    )
    words = list(result.scalars())
    if not words:
        for w in (await db.execute(select(MdpWord).where(MdpWord.session_id == session.id))).scalars():
            if exclude_id and str(w.id) == exclude_id:
                continue
            w.used = False
        words = [
            w
            for w in (await db.execute(select(MdpWord).where(MdpWord.session_id == session.id))).scalars()
            if not exclude_id or str(w.id) != exclude_id
        ]
    if not words:
        raise ValueError("Plus de mots disponibles")
    word = random.choice(words)
    word.used = True
    return word


async def _mdp_load_next_word(
    db: AsyncSession, session: GameSession, es: EventState, mdp: dict, exclude_id: str | None = None
) -> None:
    current = mdp.get("current")
    if not current:
        raise ValueError("Pas de passage actif")
    ex = exclude_id or current.get("word_id")
    word = await _mdp_pick_word(db, session, exclude_id=ex)
    current["word"] = word.word
    current["word_id"] = str(word.id)
    _save_mdp_state(es, mdp)


def _mdp_start_turn_clock(current: dict) -> None:
    current["turn_started_at"] = _mdp_now_iso()


async def _mdp_begin_playing(db: AsyncSession, session: GameSession, es: EventState, mdp: dict) -> None:
    lobby = mdp.get("lobby") or {}
    team_id = lobby.get("team_id")
    if not team_id:
        raise ValueError("Lobby introuvable")
    word = await _mdp_pick_word(db, session)
    mdp["active_team_id"] = team_id
    mdp.setdefault("team_progress", {}).setdefault(
        team_id, {"turns_completed": 0, "last_player_name": lobby.get("player_name", "Joueur")}
    )
    mdp["team_progress"][team_id]["last_player_name"] = lobby.get("player_name", "Joueur")
    mdp["current"] = {
        "phase": "playing",
        "team_id": team_id,
        "player_name": lobby.get("player_name", "Joueur"),
        "word": word.word,
        "word_id": str(word.id),
        "words_found": 0,
        "turn_points": 0,
    }
    _mdp_start_turn_clock(mdp["current"])
    _save_mdp_state(es, mdp)
    await set_module_state(db, session, "mdp", es.state)


async def _mdp_sync_countdown(db: AsyncSession, session: GameSession) -> None:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "countdown":
        return
    lobby = mdp.get("lobby") or {}
    started = lobby.get("countdown_started_at")
    if started and _mdp_countdown_remaining(started) <= 0:
        await _mdp_begin_playing(db, session, es, mdp)


async def _mdp_sync_turn(db: AsyncSession, session: GameSession) -> None:
    await _mdp_sync_countdown(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing":
        return
    scoring = await get_scoring_map(db, session.id)
    duration = _mdp_turn_duration(scoring.get("mdp"))
    if _mdp_turn_remaining(current.get("turn_started_at"), duration) > 0:
        return
    await mdp_end_turn(db, session)


async def mdp_team_present(
    db: AsyncSession, session: GameSession, team_id: str, player_id: str, player_name: str
) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    team_id = _mdp_norm_team_id(team_id)
    player_name = player_name.strip()
    player_id = player_id.strip()
    if not player_id:
        player_id = player_name
    presence = mdp.setdefault("team_presence", {})
    for other_tid, players in list(presence.items()):
        if other_tid != team_id and player_id in players:
            del players[player_id]
            if not players:
                del presence[other_tid]
    presence.setdefault(team_id, {})[player_id] = {"name": player_name, "at": _mdp_now_iso()}
    _save_mdp_state(es, mdp)
    return mdp


async def mdp_host_leave(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    if _mdp_is_active(mdp):
        raise ValueError("Un passage est en cours — terminez-le avant de changer d'équipe")
    mdp["lobby"] = None
    if not mdp.get("current"):
        mdp["active_team_id"] = None
    _save_mdp_state(es, mdp)
    await set_module_state(db, session, "mdp", es.state)
    return mdp


async def mdp_host_join(db: AsyncSession, session: GameSession, team_id: str, player_name: str) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    if _mdp_is_active(mdp):
        raise ValueError("Un passage est déjà en cours")

    team_id = _mdp_norm_team_id(team_id)
    player_name = player_name.strip()
    team_result = await db.execute(
        select(Team).where(Team.id == uuid.UUID(team_id), Team.session_id == session.id)
    )
    if not team_result.scalar_one_or_none():
        raise ValueError("Équipe introuvable")

    state = copy.deepcopy(es.state or {})
    state.pop("board", None)
    es.state = state
    flag_modified(es, "state")

    mdp = es.state.get("mdp", {"team_scores": {}})
    mdp["lobby"] = {
        "team_id": team_id,
        "player_name": player_name,
        "host_ready": True,
        "countdown_started_at": None,
    }
    mdp["active_team_id"] = team_id
    mdp["current"] = None
    _save_mdp_state(es, mdp)
    await set_module_state(db, session, "mdp", es.state)
    return mdp


async def mdp_start_countdown(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    team_id = _mdp_norm_team_id(team_id)
    lobby = mdp.get("lobby")
    if not lobby or _mdp_norm_team_id(str(lobby.get("team_id", ""))) != team_id:
        raise ValueError("L'animateur n'est pas connecté à votre équipe")
    if not lobby.get("host_ready"):
        raise ValueError("L'animateur n'est pas prêt")
    if _mdp_is_active(mdp):
        raise ValueError("Un passage est déjà en cours")

    started = _mdp_now_iso()
    lobby["countdown_started_at"] = started
    mdp["current"] = {
        "phase": "countdown",
        "team_id": team_id,
        "player_name": lobby.get("player_name", "Joueur"),
    }
    _save_mdp_state(es, mdp)
    await set_module_state(db, session, "mdp", es.state)
    return mdp


async def mdp_start_team_round(db: AsyncSession, session: GameSession, team_id: str, player_name: str) -> dict:
    """Compatibilité admin : équivaut à rejoindre l'équipe côté animateur."""
    mdp = await mdp_host_join(db, session, team_id, player_name)
    return {"lobby": mdp.get("lobby"), "message": "Animateur connecté — l'équipe peut lancer le décompte"}


async def mdp_pass_word(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing" or current.get("team_id") != team_id:
        raise ValueError("Pas de mot à passer")
    await _mdp_load_next_word(db, session, es, mdp)
    return mdp


async def mdp_validate_word(db: AsyncSession, session: GameSession) -> dict:
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing":
        raise ValueError("Pas de mot en cours")

    team_id = current["team_id"]
    scoring = await get_scoring_map(db, session.id)
    ppw = int(scoring.get("mdp", {}).get("points_per_word", 2))
    team_result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    team = team_result.scalar_one_or_none()
    if team:
        team.score_total += ppw
        record_module_points(es.state, "mdp", team_id, ppw)
    current["words_found"] = current.get("words_found", 0) + 1
    current["turn_points"] = current.get("turn_points", 0) + ppw
    await _mdp_load_next_word(db, session, es, mdp)
    await update_ranks(db, session.id)
    return mdp


async def mdp_cancel_word(db: AsyncSession, session: GameSession) -> dict:
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing":
        raise ValueError("Pas de mot en cours")
    await _mdp_load_next_word(db, session, es, mdp)
    return mdp


async def mdp_next_word(db: AsyncSession, session: GameSession) -> dict:
    """Ancienne route équipe — redirige vers passer."""
    es = await get_event_state(db, session)
    current = es.state.get("mdp", {}).get("current", {})
    team_id = current.get("team_id")
    if not team_id:
        raise ValueError("Pas de passage actif")
    mdp = await mdp_pass_word(db, session, team_id)
    cur = mdp.get("current") or {}
    return {**cur, "remaining_sec": 0}


async def mdp_end_turn(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    if "team_scores" not in mdp:
        mdp["team_scores"] = {}

    current = mdp.get("current")
    if not current:
        return mdp

    team_id = current.get("team_id")
    if not team_id:
        return mdp

    found = current.get("words_found", 0)
    points_earned = current.get("turn_points", 0)
    player_name = current.get("player_name") or (
        f"Joueur {current.get('player_index')}" if current.get("player_index") else "Joueur"
    )
    mdp["team_scores"].setdefault(team_id, [])
    mdp["team_scores"][team_id].append(
        {"player": player_name, "words": found, "points": points_earned}
    )
    mdp["last_turn"] = {
        "team_id": team_id,
        "player_name": player_name,
        "words_found": found,
        "points_earned": points_earned,
        "ended_at": _mdp_now_iso(),
    }
    progress = mdp.setdefault("team_progress", {}).setdefault(
        team_id, {"turns_completed": 0, "last_player_name": player_name}
    )
    progress["turns_completed"] = int(progress.get("turns_completed", 0)) + 1
    progress["last_player_name"] = player_name
    mdp["current"] = None
    mdp["lobby"] = None
    _save_mdp_state(es, mdp)
    await update_ranks(db, session.id)
    return mdp


def _mdp_player_payload(mdp: dict, team_id: str) -> dict[str, Any]:
    lobby = mdp.get("lobby")
    current = mdp.get("current")
    last_turn = mdp.get("last_turn")
    scoring_hint = mdp.get("points_per_word")

    if current and current.get("team_id") == team_id:
        phase = current.get("phase")
        if phase == "countdown":
            started = (lobby or {}).get("countdown_started_at")
            remaining = _mdp_countdown_remaining(started)
            return {
                "phase": "countdown",
                "active": True,
                "countdown_sec": remaining,
                "host_ready": bool((lobby or {}).get("host_ready")),
                "player_name": current.get("player_name") or (lobby or {}).get("player_name"),
                "words_found": 0,
                "turn_points": 0,
                "word": None,
                "message": f"Départ dans {remaining}…" if remaining > 0 else "C'est parti !",
            }
        if phase == "playing":
            scoring_mdp = {"turn_sec": mdp.get("turn_sec", MDP_TURN_SEC)}
            timer = _mdp_playing_timer_fields(current, scoring_mdp)
            return {
                "phase": "playing",
                "active": True,
                "word": current.get("word"),
                "words_found": current.get("words_found", 0),
                "turn_points": current.get("turn_points", 0),
                "player_name": current.get("player_name"),
                "host_ready": True,
                "remaining_sec": timer["remaining_sec"],
                "turn_duration_sec": timer["turn_duration_sec"],
                "timer_running": timer["timer_running"],
                "message": None,
            }

    if last_turn and last_turn.get("team_id") == team_id:
        return {
            "phase": "ended",
            "active": False,
            "word": None,
            "words_found": last_turn.get("words_found", 0),
            "turn_points": last_turn.get("points_earned", 0),
            "player_name": last_turn.get("player_name"),
            "message": f"Passage terminé · {last_turn.get('words_found', 0)} mot(s) · +{last_turn.get('points_earned', 0)} pt",
        }

    if lobby and lobby.get("team_id") == team_id:
        host_ready = bool(lobby.get("host_ready"))
        return {
            "phase": "lobby",
            "active": False,
            "host_ready": host_ready,
            "player_name": lobby.get("player_name"),
            "word": None,
            "words_found": 0,
            "turn_points": 0,
            "message": "Animateur connecté — appuyez sur « Prêts ! » quand tout le monde est en place."
            if host_ready
            else "Ouvrez le jeu et attendez que l'animateur se connecte à votre équipe.",
        }

    return {
        "phase": "waiting",
        "active": False,
        "host_ready": False,
        "word": None,
        "words_found": 0,
        "turn_points": 0,
        "message": "Tapez Mot de Passe et attendez l'animateur sur votre équipe.",
    }


async def mdp_player_view(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    scoring = await get_scoring_map(db, session.id)
    mdp["points_per_word"] = int(scoring.get("mdp", {}).get("points_per_word", 2))
    mdp["turn_sec"] = _mdp_turn_duration(scoring.get("mdp"))
    return _mdp_player_payload(mdp, team_id)


async def mdp_host_view(db: AsyncSession, session: GameSession) -> dict:
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    lobby = mdp.get("lobby")
    current = mdp.get("current")
    scoring = await get_scoring_map(db, session.id)
    ppw = int(scoring.get("mdp", {}).get("points_per_word", 2))
    turn_sec = _mdp_turn_duration(scoring.get("mdp"))

    payload: dict[str, Any] = {
        "team_scores": mdp.get("team_scores", {}),
        "last_turn": mdp.get("last_turn"),
        "active_team_id": mdp.get("active_team_id"),
        "team_progress": mdp.get("team_progress", {}),
        "team_presence": mdp.get("team_presence", {}),
        "lobby": lobby,
        "points_per_word": ppw,
        "turn_sec": turn_sec,
        "can_join": not _mdp_is_active(mdp),
        "can_validate": bool(current and current.get("phase") == "playing"),
        "can_end": bool(current and current.get("phase") in ("countdown", "playing")),
    }

    if current and current.get("phase") == "countdown":
        started = (lobby or {}).get("countdown_started_at")
        payload["current"] = {
            **current,
            "countdown_sec": _mdp_countdown_remaining(started),
        }
    elif current and current.get("phase") == "playing":
        payload["current"] = {
            **current,
            **_mdp_playing_timer_fields(current, {"turn_sec": turn_sec}),
        }
    else:
        payload["current"] = None

    return payload


async def mdp_expire_if_needed(db: AsyncSession, session: GameSession) -> dict | None:
    es = await get_event_state(db, session)
    was_playing = es.state.get("mdp", {}).get("current", {}).get("phase") == "playing"
    await _mdp_sync_turn(db, session)
    es = await get_event_state(db, session)
    still_playing = es.state.get("mdp", {}).get("current", {}).get("phase") == "playing"
    if was_playing and not still_playing:
        return {"expired": True}
    return None


async def mdp_finalize(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "mdp", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    mdp["finalized"] = True
    _save_mdp_state(es, mdp)
    return mdp


# ─── PAROLES ─────────────────────────────────────────────────────

async def paroles_start(db: AsyncSession, session: GameSession) -> dict:
    result = await db.execute(
        select(ParolesTrack).where(ParolesTrack.session_id == session.id, ParolesTrack.used.is_(False))
    )
    pool = list(result.scalars())
    if not pool:
        for t in (await db.execute(select(ParolesTrack).where(ParolesTrack.session_id == session.id))).scalars():
            t.used = False
        pool = list((await db.execute(select(ParolesTrack).where(ParolesTrack.session_id == session.id))).scalars())
    track = random.choice(pool)
    track.used = True
    blanks = track.display_text.count("___")
    state = {
        "phase": "listening",
        "track_id": str(track.id),
        "title": track.title,
        "audio_url": track.audio_url,
        "display_text": track.display_text,
        "blank_count": blanks,
        "listen_count": 0,
        "team_answers": {},
        "locked": {},
        "revealed": False,
    }
    es = await get_event_state(db, session)
    es.state = {**es.state, "paroles": state}
    await set_module_state(db, session, "paroles", es.state)
    return state


async def paroles_listen(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    paroles = es.state.get("paroles", {})
    paroles["listen_count"] = paroles.get("listen_count", 0) + 1
    if paroles["listen_count"] >= 1:
        paroles["phase"] = "writing"
    es.state = {**es.state, "paroles": paroles}
    return paroles


async def paroles_submit(db: AsyncSession, session: GameSession, team_id: str, answers: list[str]) -> dict:
    es = await get_event_state(db, session)
    paroles = es.state.get("paroles", {})
    paroles.setdefault("team_answers", {})[team_id] = answers
    paroles.setdefault("locked", {})[team_id] = True
    es.state = {**es.state, "paroles": paroles}
    return paroles


async def paroles_score(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    paroles = es.state.get("paroles", {})
    tid = uuid.UUID(paroles["track_id"])
    result = await db.execute(select(ParolesTrack).where(ParolesTrack.id == tid))
    track = result.scalar_one()
    scoring = await get_scoring_map(db, session.id)
    ppw = scoring.get("paroles", {}).get("points_per_word", 1)
    expected = track.answers
    teams_result = await db.execute(select(Team).where(Team.session_id == session.id))
    teams = {str(t.id): t for t in teams_result.scalars()}
    results = {}
    for team_id, answers in paroles.get("team_answers", {}).items():
        score = 0
        for i, exp in enumerate(expected):
            if i < len(answers) and answers[i].strip().lower() == exp.strip().lower():
                score += ppw
        if team_id in teams:
            teams[team_id].score_total += score
            record_module_points(es.state, "paroles", team_id, score)
        results[team_id] = {"score": score, "answers": answers}
    paroles["revealed"] = True
    paroles["phase"] = "done"
    paroles["results"] = results
    paroles["expected"] = expected
    es.state = {**es.state, "paroles": paroles}
    await update_ranks(db, session.id)
    return paroles


# ─── CHIPS ───────────────────────────────────────────────────────

async def chips_start_round(db: AsyncSession, session: GameSession, chip_id: str, flavors_to_guess: list[str]) -> dict:
    cid = uuid.UUID(chip_id)
    result = await db.execute(select(ChipItem).where(ChipItem.id == cid))
    chip = result.scalar_one()
    state = {
        "phase": "tasting",
        "chip_id": chip_id,
        "chip_name": chip.name,
        "all_flavors": chip.flavors,
        "flavors_to_guess": flavors_to_guess,
        "team_guesses": {},
        "results": {},
    }
    es = await get_event_state(db, session)
    es.state = {**es.state, "chips": state}
    await set_module_state(db, session, "chips", es.state)
    return {**state, "all_flavors": None}  # hide from broadcast


async def chips_submit_guesses(db: AsyncSession, session: GameSession, team_id: str, guesses: list[str]) -> dict:
    es = await get_event_state(db, session)
    chips = es.state.get("chips", {})
    chips.setdefault("team_guesses", {})[team_id] = guesses
    es.state = {**es.state, "chips": chips}
    return chips


async def chips_score_team(
    db: AsyncSession, session: GameSession, team_id: str, correct_flavors: list[str], wrong_count: int
) -> dict:
    es = await get_event_state(db, session)
    chips = es.state.get("chips", {})
    scoring = await get_scoring_map(db, session.id)
    chips_cfg = scoring.get("chips", {})
    malus = chips_cfg.get("malus_per_wrong", 1)
    ppc = chips_cfg.get("points_per_correct", 1)
    correct_pts = len(correct_flavors) * int(ppc)
    penalty = wrong_count * malus
    net = max(0, correct_pts - penalty)
    result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    team = result.scalar_one()
    team.score_total += net
    record_module_points(es.state, "chips", team_id, net)
    chips.setdefault("results", {})[team_id] = {
        "correct": correct_flavors,
        "wrong_count": wrong_count,
        "correct_points": correct_pts,
        "penalty": penalty,
        "points": net,
    }
    es.state = {**es.state, "chips": chips}
    await update_ranks(db, session.id)
    return chips


async def chips_finalize(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "chips", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    chips = es.state.get("chips", {})
    chips["finalized"] = True
    chips["episode_placement"] = placement
    es.state = {**es.state, "chips": chips}
    return chips


# ─── MOLKKY / PISCINE ───────────────────────────────────────────

async def molkky_submit(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "molkky", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    es.state = {**es.state, "molkky": {"placement": placement, "done": True}}
    return es.state["molkky"]


async def piscine_submit(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "piscine", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    es.state = {**es.state, "piscine": {"placement": placement, "done": True}}
    return es.state["piscine"]


async def poignards_display(db: AsyncSession, session: GameSession) -> dict:
    await update_ranks(db, session.id)
    result = await db.execute(
        select(Team).where(Team.session_id == session.id).order_by(Team.score_total.desc())
    )
    teams = list(result.scalars())
    scoring = await get_scoring_map(db, session.id)
    handicaps = scoring.get("poignards", {}).get("handicap_seconds", {"1": 0, "2": 15, "3": 30})
    data = {
        "ranking": [
            {
                "team_id": str(t.id),
                "name": t.name,
                "color": t.color,
                "rank": i + 1,
                "score": t.score_total,
                "handicap_seconds": handicaps.get(str(i + 1), 0),
            }
            for i, t in enumerate(teams)
        ]
    }
    es = await get_event_state(db, session)
    es.state = {**es.state, "poignards": data}
    await set_module_state(db, session, "poignards", es.state)
    return data
