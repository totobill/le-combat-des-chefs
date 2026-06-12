import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SessionStatus(str, enum.Enum):
    SETUP = "setup"
    ACTIVE = "active"
    FINISHED = "finished"


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=SessionStatus.SETUP.value)
    current_module: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    teams: Mapped[list["Team"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    scoring_configs: Mapped[list["ScoringConfig"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    event_state: Mapped["EventState | None"] = relationship(
        back_populates="session", uselist=False, cascade="all, delete-orphan"
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game_sessions.id"))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default="#5b5ef5")
    member_count: Mapped[int] = mapped_column(Integer, default=5)
    score_total: Mapped[int] = mapped_column(Integer, default=0)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eliminated: Mapped[bool] = mapped_column(default=False)

    session: Mapped["GameSession"] = relationship(back_populates="teams")


class ScoringConfig(Base):
    __tablename__ = "scoring_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game_sessions.id"))
    module: Mapped[str] = mapped_column(String(32))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)

    session: Mapped["GameSession"] = relationship(back_populates="scoring_configs")


class ScoreEvent(Base):
    __tablename__ = "score_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("game_sessions.id"))
    module: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventState(Base):
    __tablename__ = "event_state"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), primary_key=True
    )
    module: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state: Mapped[dict] = mapped_column(JSONB, default=dict)

    session: Mapped["GameSession"] = relationship(back_populates="event_state")


class DccQuestion(Base):
    __tablename__ = "dcc_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(100), default="Culture générale")
    duo_opts: Mapped[list] = mapped_column(JSONB)
    duo_correct: Mapped[int] = mapped_column(Integer)
    carre_opts: Mapped[list] = mapped_column(JSONB)
    carre_correct: Mapped[int] = mapped_column(Integer)
    cash_answer: Mapped[str] = mapped_column(String(500))
    cash_aliases: Mapped[list] = mapped_column(JSONB, default=list)
    used: Mapped[bool] = mapped_column(default=False)


class MdpWord(Base):
    __tablename__ = "mdp_words"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=True
    )
    word: Mapped[str] = mapped_column(String(200))
    used: Mapped[bool] = mapped_column(default=False)


class ParolesTrack(Base):
    __tablename__ = "paroles_tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    display_text: Mapped[str] = mapped_column(Text)
    answers: Mapped[list] = mapped_column(JSONB)
    used: Mapped[bool] = mapped_column(default=False)


class ChipItem(Base):
    __tablename__ = "chip_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_sessions.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    flavors: Mapped[list] = mapped_column(JSONB)
    used: Mapped[bool] = mapped_column(default=False)
