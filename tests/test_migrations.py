from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlmodel import SQLModel

from app.database import create_db_engine, init_db


def test_migrations_match_models() -> None:
    """Fails when a model changes without a new Alembic revision."""
    engine = create_db_engine("sqlite://")
    init_db(engine)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), SQLModel.metadata)
    assert diff == []
    init_db(engine)  # re-running is a no-op
