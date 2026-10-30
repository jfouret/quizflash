from alembic import context
from sqlalchemy.engine import Connection
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers tables on SQLModel.metadata)
from app.database import DATABASE_URL, create_db_engine

config = context.config


def run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=SQLModel.metadata,
        render_as_batch=True,  # SQLite needs table rebuilds for most ALTERs
    )
    with context.begin_transaction():
        context.run_migrations()


connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    with create_db_engine(config.get_main_option("sqlalchemy.url") or DATABASE_URL).begin() as conn:
        run(conn)
