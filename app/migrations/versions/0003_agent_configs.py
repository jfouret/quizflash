"""agent configs

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agentconfig",
        sa.Column("step", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("base_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("api_key_env", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("voice", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("system_prompt", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("prompt_template", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("step"),
    )


def downgrade() -> None:
    op.drop_table("agentconfig")
