"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, index=True),
        sa.Column("status", sa.String(20)),
        sa.Column("current_module", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id")),
        sa.Column("name", sa.String(100)),
        sa.Column("color", sa.String(20)),
        sa.Column("member_count", sa.Integer()),
        sa.Column("score_total", sa.Integer()),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("eliminated", sa.Boolean()),
    )
    op.create_table(
        "scoring_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id")),
        sa.Column("module", sa.String(32)),
        sa.Column("config", postgresql.JSONB()),
    )
    op.create_table(
        "score_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id")),
        sa.Column("module", sa.String(32)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "event_state",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id"), primary_key=True),
        sa.Column("module", sa.String(32), nullable=True),
        sa.Column("state", postgresql.JSONB()),
    )
    op.create_table(
        "dcc_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id"), nullable=True),
        sa.Column("question", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("duo_opts", postgresql.JSONB()),
        sa.Column("duo_correct", sa.Integer()),
        sa.Column("carre_opts", postgresql.JSONB()),
        sa.Column("carre_correct", sa.Integer()),
        sa.Column("cash_answer", sa.String(500)),
        sa.Column("cash_aliases", postgresql.JSONB()),
        sa.Column("used", sa.Boolean()),
    )
    op.create_table(
        "mdp_words",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id"), nullable=True),
        sa.Column("word", sa.String(200)),
        sa.Column("used", sa.Boolean()),
    )
    op.create_table(
        "paroles_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id"), nullable=True),
        sa.Column("title", sa.String(200)),
        sa.Column("audio_url", sa.String(500), nullable=True),
        sa.Column("display_text", sa.Text()),
        sa.Column("answers", postgresql.JSONB()),
        sa.Column("used", sa.Boolean()),
    )
    op.create_table(
        "chip_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_sessions.id"), nullable=True),
        sa.Column("name", sa.String(200)),
        sa.Column("flavors", postgresql.JSONB()),
        sa.Column("used", sa.Boolean()),
    )


def downgrade() -> None:
    op.drop_table("chip_items")
    op.drop_table("paroles_tracks")
    op.drop_table("mdp_words")
    op.drop_table("dcc_questions")
    op.drop_table("event_state")
    op.drop_table("score_events")
    op.drop_table("scoring_configs")
    op.drop_table("teams")
    op.drop_table("game_sessions")
