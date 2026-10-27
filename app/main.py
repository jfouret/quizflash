from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session

from app.crud import NotFoundError
from app.database import DATABASE_URL, create_db_engine, init_db
from app.judge.openrouter import OpenRouterJudge
from app.mcp_server import create_mcp
from app.routes import cards, decks, pages, settings, stats, study, tags
from app.stt.openai_compat import OpenAICompatibleSTT


def create_app(database_url: str | None = None) -> FastAPI:
    engine = create_db_engine(database_url or DATABASE_URL)
    mcp_server = create_mcp(lambda: Session(engine))
    mcp_app = mcp_server.http_app(path="/")

    @asynccontextmanager
    async def app_lifespan(application: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        async with mcp_app.lifespan(application):
            yield

    app = FastAPI(
        title="QuizDeck",
        version="0.1.0",
        lifespan=app_lifespan,
    )
    app.state.engine = engine
    app.state.mcp = mcp_server
    app.state.fallback_tokens = {}
    app.state.judge = OpenRouterJudge.from_env()
    app.state.stt = OpenAICompatibleSTT.from_env()

    app.include_router(decks.router)
    app.include_router(cards.router)
    app.include_router(tags.router)
    app.include_router(study.router)
    app.include_router(stats.router)
    app.include_router(settings.router)
    app.include_router(pages.router)

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid_value(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.mount("/mcp", mcp_app)
    return app


app = create_app()
