"""queue mode setting

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("queue_mode", sa.String(), nullable=False, server_default="priority"),
    )


def downgrade() -> None:
    op.drop_column("settings", "queue_mode")
