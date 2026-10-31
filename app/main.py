import mimetypes
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.auth import ApiTokenVerifier, AuthConfig, LoginThrottle
from app.crud import NotFoundError, PermissionDeniedError
from app.database import DATABASE_URL, create_db_engine, init_db
from app.dependencies import LoginRequiredError
from app.judge.openrouter import OpenRouterJudge
from app.mcp_server import create_mcp
from app.routes import admin, auth, cards, decks, history, pages, settings, stats, study, tags
from app.stt.openai_compat import OpenAICompatibleSTT
from app.teacher.base import Teacher
from app.teacher.openrouter import OpenRouterTeacher
from app.templating import templates
from app.tts.openrouter import OpenRouterTTS

mimetypes.add_type("application/manifest+json", ".webmanifest")

ROUTERS = (
    auth.router,
    decks.router,
    decks.public_router,
    cards.router,
    tags.router,
    study.router,
    stats.router,
    history.router,
    settings.router,
    admin.router,
    pages.router,
)

ERROR_TITLES = {400: "Invalid request", 403: "Not allowed", 404: "Not found"}

# Strict policy: every script and stylesheet is served by the app itself.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
# The generated API docs load Swagger UI / ReDoc from a CDN and use inline bootstrap code.
DOCS_PATHS = {"/docs", "/redoc", "/docs/oauth2-redirect"}
DOCS_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=(), payment=()",
}


def create_app(
    database_url: str | None = None,
    teacher: Teacher | None = None,
    auth_config: AuthConfig | None = None,
) -> FastAPI:
    engine = create_db_engine(database_url or DATABASE_URL)
    config = auth_config or AuthConfig.from_env()
    teacher_instance = teacher or OpenRouterTeacher.from_env()
    mcp_server = create_mcp(lambda: Session(engine), teacher_instance, ApiTokenVerifier(engine))
    mcp_app = mcp_server.http_app(path="/", json_response=True, stateless_http=True)

    @asynccontextmanager
    async def app_lifespan(application: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        async with mcp_app.lifespan(application):
            yield

    app = FastAPI(
        title="QuizDeck",
        version=__version__,
        lifespan=app_lifespan,
    )
    app.state.engine = engine
    app.state.mcp = mcp_server
    app.state.auth_config = config
    app.state.login_throttle = LoginThrottle()
    app.state.fallback_tokens = {}
    app.state.judge = OpenRouterJudge.from_env()
    app.state.stt = OpenAICompatibleSTT.from_env()
    app.state.teacher = teacher_instance
    app.state.tts = OpenRouterTTS.from_env()

    if config.oidc_enabled:
        oauth = OAuth()
        oauth.register(
            "oidc",
            client_id=config.oidc_client_id,
            client_secret=config.oidc_client_secret,
            server_metadata_url=(
                f"{(config.oidc_issuer or '').rstrip('/')}/.well-known/openid-configuration"
            ),
            client_kwargs={"scope": config.oidc_scopes, "code_challenge_method": "S256"},
        )
        app.state.oauth = oauth
        # Only holds OIDC state/nonce/PKCE verifier during the login round trip.
        app.add_middleware(
            SessionMiddleware,
            secret_key=config.secret_key,
            session_cookie="quizdeck_oidc",
            max_age=600,
            same_site="lax",
            https_only=config.cookie_secure,
        )

    for router in ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        docs = request.url.path in DOCS_PATHS
        response.headers.setdefault(
            "Content-Security-Policy",
            DOCS_CONTENT_SECURITY_POLICY if docs else CONTENT_SECURITY_POLICY,
        )
        if config.cookie_secure:
            # Only sent over HTTPS, so plain-HTTP local development is unaffected.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        if not request.url.path.startswith("/static"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    def _is_api(request: Request) -> bool:
        return request.url.path.startswith(("/api", "/mcp"))

    def _error(request: Request, status_code: int, detail: str) -> Response:
        if _is_api(request):
            return JSONResponse(status_code=status_code, content={"detail": detail})
        return templates.TemplateResponse(
            request=request,
            name="message.html",
            context={"message": detail, "title": ERROR_TITLES.get(status_code, "Error")},
            status_code=status_code,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if _is_api(request):
            return await http_exception_handler(request, exc)
        return _error(request, exc.status_code, str(exc.detail))

    @app.exception_handler(LoginRequiredError)
    async def login_required(request: Request, _: LoginRequiredError) -> Response:
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})
        return RedirectResponse("/login", status_code=303)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> Response:
        return _error(request, 404, str(exc))

    @app.exception_handler(PermissionDeniedError)
    async def forbidden(request: Request, exc: PermissionDeniedError) -> Response:
        return _error(request, 403, str(exc))

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, exc: ValueError) -> Response:
        return _error(request, 400, str(exc))

    app.mount("/mcp", mcp_app)
    app.mount(
        "/static",
        StaticFiles(directory=str(Path(__file__).parent / "static")),
        name="static",
    )
    return app


app = create_app()
