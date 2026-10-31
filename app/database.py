import os
from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.agents import AGENT_STEPS, DEFAULT_AGENT_CONFIGS
from app.models import AgentConfig, AppSettings

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quizdeck.db")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def create_db_engine(database_url: str = DATABASE_URL) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url in {"sqlite://", "sqlite:///:memory:"}:
        engine = create_engine(database_url, connect_args=connect_args, poolclass=StaticPool)
    else:
        engine = create_engine(database_url, connect_args=connect_args)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def init_db(engine: Engine) -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    with Session(engine) as session:
        if session.get(AppSettings, 1) is None:
            session.add(AppSettings())
        for step in AGENT_STEPS:
            if session.get(AgentConfig, step) is None:
                session.add(AgentConfig(step=step, **DEFAULT_AGENT_CONFIGS[step]))
        session.commit()


def get_session(request: Request) -> Generator[Session]:
    engine: Engine = request.app.state.engine
    with Session(engine) as session:
        yield session
