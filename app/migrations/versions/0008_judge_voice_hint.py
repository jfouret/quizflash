"""tell the judge when an answer was spoken

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-21 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = """Is the user's answer substantively correct for the question?

Question: {{ card.question }}
Expected answer: {{ card.answer }}
User answer: {{ user_answer }}"""

NEW = OLD + """{% if input_method == 'voice' %}

The answer was spoken aloud and transcribed by speech-to-text. Judge the meaning only: ignore spelling, punctuation, formatting and code syntax (nobody dictates code symbols), and tolerate misheard technical terms when the intent is clear.{% endif %}"""


def _swap(old: str, new: str) -> None:
    # Only the untouched default is replaced: an admin's customised prompt stays.
    op.get_bind().execute(
        sa.text(
            "UPDATE agentconfig SET prompt_template = :new "
            "WHERE step = 'judge' AND prompt_template = :old"
        ),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    _swap(OLD, NEW)


def downgrade() -> None:
    _swap(NEW, OLD)
