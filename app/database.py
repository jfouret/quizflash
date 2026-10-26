import os
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.models import Settings

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./quizdeck.db")


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


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        if session.get(Settings, 1) is None:
            session.add(Settings())
            session.commit()


def get_session(request: Request) -> Generator[Session]:
    engine: Engine = request.app.state.engine
    with Session(engine) as session:
        yield session
