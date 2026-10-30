import logging
from typing import Annotated, Any

from authlib.integrations.starlette_client import OAuthError
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import auth, crud
from app.auth import AuthConfig
from app.dependencies import AuthConfigDep, CurrentUser, SessionDep, check_origin
from app.models import User
from app.schemas import MeResponse, UserRead
from app.templating import templates

router = APIRouter()
logger = logging.getLogger(__name__)

STATUS_MESSAGES = {
    "pending": "Your account is waiting for administrator approval.",
    "disabled": "Your account is suspended. Contact an administrator.",
}


def _page(request: Request, name: str, status_code: int = 200, **context: Any) -> Response:
    return templates.TemplateResponse(
        request=request, name=name, context=context, status_code=status_code
    )


def _start_session(
    request: Request, session: SessionDep, user: User, config: AuthConfig
) -> RedirectResponse:
    old = request.cookies.get(config.cookie_name)
    if old:
        auth.delete_session(session, old)
    token = auth.create_session(session, user, request.headers.get("user-agent", ""), config)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        config.cookie_name,
        token,
        max_age=int(config.session_max.total_seconds()),
        path="/",
        secure=config.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response


def _local_only(config: AuthConfig) -> None:
    if config.oidc_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, session: SessionDep, config: AuthConfigDep) -> Response:
    return _page(
        request,
        "login.html",
        oidc_enabled=config.oidc_enabled,
        registration=crud.get_app_settings(session).registration,
    )


@router.post("/login", include_in_schema=False)
def login(
    request: Request,
    session: SessionDep,
    config: AuthConfigDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    _local_only(config)
    check_origin(request)
    throttle: auth.LoginThrottle = request.app.state.login_throttle
    key = f"{request.client.host if request.client else ''}|{email.strip().lower()}"
    registration = crud.get_app_settings(session).registration
    if throttle.blocked(key):
        return _page(
            request, "login.html", 429, error="Too many attempts. Try again later.",
            oidc_enabled=False, registration=registration,
        )
    user = auth.authenticate_local(session, email, password)
    if user is None:
        throttle.fail(key)
        return _page(
            request, "login.html", 400, error="Invalid email or password.",
            oidc_enabled=False, registration=registration,
        )
    throttle.reset(key)
    if user.status != "active":
        return _page(request, "message.html", 403, message=STATUS_MESSAGES[user.status])
    return _start_session(request, session, user, config)


@router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
def signup_page(request: Request, session: SessionDep, config: AuthConfigDep) -> Response:
    _local_only(config)
    if crud.get_app_settings(session).registration == "closed":
        return _page(request, "message.html", 403, message="Registration is closed.")
    return _page(request, "signup.html")


@router.post("/signup", include_in_schema=False)
def signup(
    request: Request,
    session: SessionDep,
    config: AuthConfigDep,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    display_name: Annotated[str, Form()] = "",
) -> Response:
    _local_only(config)
    check_origin(request)
    registration = crud.get_app_settings(session).registration
    if registration == "closed":
        return _page(request, "message.html", 403, message="Registration is closed.")
    try:
        user = auth.create_local_user(
            session,
            email=email,
            password=password,
            display_name=display_name,
            status="active" if registration == "open" else "pending",
        )
    except ValueError as exc:
        return _page(request, "signup.html", 400, error=str(exc))
    if user.status != "active":
        return _page(request, "message.html", message=STATUS_MESSAGES[user.status])
    return _start_session(request, session, user, config)


@router.post("/logout", include_in_schema=False)
def logout(
    request: Request, session: SessionDep, _: CurrentUser, config: AuthConfigDep
) -> RedirectResponse:
    auth.delete_session(session, request.state.session_token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        config.cookie_name, path="/", secure=config.cookie_secure, httponly=True, samesite="lax"
    )
    return response


@router.get("/auth/oidc/login", include_in_schema=False)
async def oidc_login(request: Request, config: AuthConfigDep) -> Response:
    if not config.oidc_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    redirect_uri = str(request.url_for("oidc_callback"))
    response: Response = await request.app.state.oauth.oidc.authorize_redirect(
        request, redirect_uri
    )
    return response


@router.get("/auth/oidc/callback", name="oidc_callback", include_in_schema=False)
async def oidc_callback(request: Request, session: SessionDep, config: AuthConfigDep) -> Response:
    if not config.oidc_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    client = request.app.state.oauth.oidc
    try:
        token = await client.authorize_access_token(request)
        claims = dict(token.get("userinfo") or {})
        if auth.oidc_role(claims, config) != "admin" and "access_token" in token:
            # Some IdPs only expose roles through the userinfo endpoint.
            claims = {**dict(await client.userinfo(token=token)), **claims}
    except OAuthError as exc:
        logger.warning("OIDC callback failed: %s", exc)
        return _page(request, "message.html", 400, message="Single sign-on failed. Try again.")
    try:
        user = auth.provision_oidc_user(session, claims, config)
    except (PermissionError, ValueError) as exc:
        return _page(request, "message.html", 403, message=str(exc))
    if user.status != "active":
        return _page(request, "message.html", 403, message=STATUS_MESSAGES[user.status])
    return _start_session(request, session, user, config)


@router.get("/api/auth/me", response_model=MeResponse, tags=["auth"])
def me(request: Request, user: CurrentUser) -> MeResponse:
    return MeResponse(user=UserRead.model_validate(user), csrf_token=request.state.csrf_token)
