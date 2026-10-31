"""per-deck grading scale and stored teacher explanations

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31 16:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "deck",
        sa.Column("grading_scale", sa.JSON(), nullable=True, server_default="{}"),
    )
    op.add_column(
        "answerlog",
        sa.Column(
            "explanation", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default=""
        ),
    )


def downgrade() -> None:
    op.drop_column("answerlog", "explanation")
    op.drop_column("deck", "grading_scale")
