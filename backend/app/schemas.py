from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    password: str


class JoinRequest(BaseModel):
    session_code: str
    team_id: UUID
    display_name: str = Field(min_length=1, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    team_id: str | None = None
    display_name: str | None = None


class TeamUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    member_count: int | None = None


class ScoringUpdate(BaseModel):
    config: dict[str, Any]


class PlacementSubmit(BaseModel):
    placement: dict[str, int]  # team_id -> rank 1,2,3


class DccQuestionCreate(BaseModel):
    question: str
    category: str = "Culture générale"
    duo_opts: list[str]
    duo_correct: int
    carre_opts: list[str]
    carre_correct: int
    cash_answer: str
    cash_aliases: list[str] = []


class DccChooseRequest(BaseModel):
    mode: str  # duo, carre, cash


class DccAnswerRequest(BaseModel):
    answer: str | int  # index for duo/carre, string for cash


class MdpStartRound(BaseModel):
    team_id: UUID
    player_index: int


class MdpNextWord(BaseModel):
    pass


class ParolesSubmit(BaseModel):
    answers: list[str]


class ChipsStartRequest(BaseModel):
    chip_id: str
    flavors_to_guess: list[str]


class ChipsSubmit(BaseModel):
    guesses: list[str]


class ChipsScoreRequest(BaseModel):
    team_id: UUID
    correct_flavors: list[str]
    wrong_count: int = 0


class MolkkyMatchResult(BaseModel):
    scores: dict[str, int]  # team_id -> molkky score
    placement: dict[str, int]


class PiscineResult(BaseModel):
    placement: dict[str, int]


class ModuleStart(BaseModel):
    module: str
