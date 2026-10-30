"""tts settings

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "appsettings",
        sa.Column("tts_allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "settings",
        sa.Column("tts_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "settings",
        sa.Column("question_vocal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "settings",
        sa.Column("teacher_vocal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("settings", "teacher_vocal")
    op.drop_column("settings", "question_vocal")
    op.drop_column("settings", "tts_enabled")
    op.drop_column("appsettings", "tts_allowed")
