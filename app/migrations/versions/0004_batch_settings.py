"""batch study settings

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31 14:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("batch_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "settings",
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="5"),
    )


def downgrade() -> None:
    op.drop_column("settings", "batch_size")
    op.drop_column("settings", "batch_enabled")
