import random
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

async def dcc_start_question(db: AsyncSession, session: GameSession) -> dict:
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
        pool = list((await db.execute(
            select(DccQuestion).where(DccQuestion.session_id == session.id)
        )).scalars())
    question = random.choice(pool)
    question.used = True
    state = {
        "phase": "choosing",
        "question_id": str(question.id),
        "question": question.question,
        "category": question.category,
        "team_choices": {},
        "team_answers": {},
        "revealed": False,
        "results": {},
    }
    await set_module_state(db, session, "dcc", {**(await get_event_state(db, session)).state, "dcc": state})
    return state


async def dcc_team_choose(db: AsyncSession, session: GameSession, team_id: str, mode: str) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    if dcc.get("phase") != "choosing":
        raise ValueError("Phase invalide")
    if mode not in ("duo", "carre", "cash"):
        raise ValueError("Mode invalide")
    dcc["team_choices"][team_id] = mode
    if len(dcc["team_choices"]) >= 3:
        dcc["phase"] = "answering"
    es.state = {**es.state, "dcc": dcc}
    return dcc


async def dcc_get_question_for_team(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    qid = uuid.UUID(dcc["question_id"])
    result = await db.execute(select(DccQuestion).where(DccQuestion.id == qid))
    question = result.scalar_one()
    mode = dcc["team_choices"].get(team_id)
    if not mode:
        return {"phase": dcc.get("phase"), "question": dcc.get("question"), "mode": None}
    if mode == "duo":
        opts = question.duo_opts
    elif mode == "carre":
        opts = question.carre_opts
    else:
        opts = None
    return {
        "phase": dcc.get("phase"),
        "question": question.question,
        "category": question.category,
        "mode": mode,
        "options": opts,
    }


async def dcc_team_answer(db: AsyncSession, session: GameSession, team_id: str, answer: Any) -> dict:
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    dcc.setdefault("team_answers", {})[team_id] = answer
    es.state = {**es.state, "dcc": dcc}
    return dcc


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
    es.state = {**es.state, "dcc": dcc}
    await update_ranks(db, session.id)
    return dcc


async def dcc_finalize(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "dcc", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    dcc = es.state.get("dcc", {})
    dcc["finalized"] = True
    dcc["episode_placement"] = placement
    es.state = {**es.state, "dcc": dcc}
    return dcc


# ─── MDP ───────────────────────────────────────────────────────────

def _mdp_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _mdp_remaining_sec(current: dict) -> int:
    from datetime import UTC, datetime

    started = current.get("started_at")
    if not started:
        return 0
    duration = int(current.get("duration_sec", 30))
    started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
    elapsed = (datetime.now(UTC) - started_dt).total_seconds()
    return max(0, int(duration - elapsed))


def _mdp_is_playing(mdp: dict) -> bool:
    current = mdp.get("current")
    return bool(current and current.get("phase") == "playing")


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


async def mdp_expire_if_needed(db: AsyncSession, session: GameSession) -> dict | None:
    """Clôture le passage si les 30 s sont écoulées."""
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing":
        return None
    if _mdp_remaining_sec(current) > 0:
        return None
    return await mdp_end_turn(db, session)


async def mdp_start_team_round(db: AsyncSession, session: GameSession, team_id: str, player_index: int) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})

    await mdp_expire_if_needed(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})

    if _mdp_is_playing(mdp):
        raise ValueError("Un passage est encore en cours — attendez la fin des 30 secondes")

    word = await _mdp_pick_word(db, session)
    mdp["current"] = {
        "team_id": team_id,
        "player_index": player_index,
        "word": word.word,
        "word_id": str(word.id),
        "words_found": 0,
        "started_at": _mdp_now_iso(),
        "duration_sec": 30,
        "phase": "playing",
    }
    mdp.pop("last_turn", None)
    es.state = {**es.state, "mdp": mdp}
    await set_module_state(db, session, "mdp", es.state)
    return {**mdp["current"], "remaining_sec": 30}


async def mdp_next_word(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    if not current or current.get("phase") != "playing":
        raise ValueError("Pas de passage actif")
    if _mdp_remaining_sec(current) <= 0:
        raise ValueError("Temps écoulé")

    word = await _mdp_pick_word(db, session, exclude_id=current.get("word_id"))
    current["words_found"] = current.get("words_found", 0) + 1
    current["word"] = word.word
    current["word_id"] = str(word.id)
    es.state = {**es.state, "mdp": mdp}
    return {**current, "remaining_sec": _mdp_remaining_sec(current)}


async def mdp_end_turn(db: AsyncSession, session: GameSession) -> dict:
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    if "team_scores" not in mdp:
        mdp["team_scores"] = {}

    current = mdp.get("current")
    if not current:
        return mdp

    if current.get("phase") == "ended":
        return mdp

    team_id = current["team_id"]
    found = current.get("words_found", 0)
    scoring = await get_scoring_map(db, session.id)
    ppw = int(scoring.get("mdp", {}).get("points_per_word", 2))
    points_earned = found * ppw
    team_result = await db.execute(select(Team).where(Team.id == uuid.UUID(team_id)))
    team = team_result.scalar_one_or_none()
    if team:
        team.score_total += points_earned
        record_module_points(es.state, "mdp", team_id, points_earned)
    mdp["team_scores"].setdefault(team_id, [])
    mdp["team_scores"][team_id].append(
        {"player": current["player_index"], "words": found, "points": points_earned}
    )
    mdp["last_turn"] = {
        "team_id": team_id,
        "player_index": current["player_index"],
        "words_found": found,
        "points_earned": points_earned,
        "ended_at": _mdp_now_iso(),
    }
    mdp["current"] = None
    es.state = {**es.state, "mdp": mdp}
    await update_ranks(db, session.id)
    return mdp


async def mdp_player_view(db: AsyncSession, session: GameSession, team_id: str) -> dict:
    await mdp_expire_if_needed(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    current = mdp.get("current")
    last_turn = mdp.get("last_turn")

    if not current or current.get("team_id") != team_id:
        if last_turn and last_turn.get("team_id") == team_id:
            return {
                "phase": "ended",
                "active": False,
                "word": None,
                "words_found": last_turn.get("words_found", 0),
                "player_index": last_turn.get("player_index"),
                "remaining_sec": 0,
                "message": "Temps écoulé ! En attente du prochain joueur.",
            }
        return {
            "phase": "waiting",
            "active": False,
            "word": None,
            "words_found": 0,
            "remaining_sec": 0,
            "message": "En attente que l'animateur lance votre passage.",
        }

    remaining = _mdp_remaining_sec(current)
    if remaining <= 0:
        await mdp_end_turn(db, session)
        return await mdp_player_view(db, session, team_id)

    return {
        "phase": "playing",
        "active": True,
        "word": current.get("word"),
        "words_found": current.get("words_found", 0),
        "player_index": current.get("player_index"),
        "remaining_sec": remaining,
        "duration_sec": current.get("duration_sec", 30),
        "started_at": current.get("started_at"),
    }


async def mdp_host_view(db: AsyncSession, session: GameSession) -> dict:
    await mdp_expire_if_needed(db, session)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {"team_scores": {}})
    current = mdp.get("current")
    payload: dict[str, Any] = {
        "team_scores": mdp.get("team_scores", {}),
        "last_turn": mdp.get("last_turn"),
        "can_start": not _mdp_is_playing(mdp),
    }
    if current and current.get("phase") == "playing":
        payload["current"] = {**current, "remaining_sec": _mdp_remaining_sec(current)}
    else:
        payload["current"] = None
    return payload


async def mdp_finalize(db: AsyncSession, session: GameSession, placement: dict[str, int]) -> dict:
    await apply_placement_points(db, session, "mdp", placement)
    await update_ranks(db, session.id)
    es = await get_event_state(db, session)
    mdp = es.state.get("mdp", {})
    mdp["finalized"] = True
    es.state = {**es.state, "mdp": mdp}
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
