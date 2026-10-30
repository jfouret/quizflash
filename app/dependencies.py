import hmac
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.auth import AuthConfig, resolve_session
from app.database import get_session
from app.judge.base import Judge
from app.models import User
from app.stt.base import STTProvider
from app.teacher.base import Teacher

SessionDep = Annotated[Session, Depends(get_session)]
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LoginRequiredError(Exception):
    """Raised when no valid browser session is present."""


def get_auth_config(request: Request) -> AuthConfig:
    return cast(AuthConfig, request.app.state.auth_config)


AuthConfigDep = Annotated[AuthConfig, Depends(get_auth_config)]


def check_origin(request: Request) -> None:
    """Reject cross-site unsafe requests when the browser tells us the origin."""
    origin = request.headers.get("origin")
    if request.method in SAFE_METHODS or origin is None:
        return
    if origin.split("://", 1)[-1] != request.url.netloc:
        raise HTTPException(status_code=403, detail="Cross-origin request rejected")


async def current_user(request: Request, session: SessionDep, config: AuthConfigDep) -> User:
    token = request.cookies.get(config.cookie_name)
    resolved = resolve_session(session, token, config) if token else None
    if resolved is None:
        raise LoginRequiredError()
    auth_session, user = resolved
    if request.method not in SAFE_METHODS:
        check_origin(request)
        sent = request.headers.get("x-csrf-token")
        if sent is None and request.headers.get("content-type", "").startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")
        ):
            field = (await request.form()).get("csrf_token")
            sent = field if isinstance(field, str) else None
        if not sent or not hmac.compare_digest(sent, auth_session.csrf_token):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
    request.state.user = user
    request.state.csrf_token = auth_session.csrf_token
    request.state.session_token = token
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_judge(request: Request) -> Judge:
    return cast(Judge, request.app.state.judge)


def get_stt(request: Request) -> STTProvider:
    return cast(STTProvider, request.app.state.stt)


def get_teacher(request: Request) -> Teacher:
    return cast(Teacher, request.app.state.teacher)


JudgeDep = Annotated[Judge, Depends(get_judge)]
STTDep = Annotated[STTProvider, Depends(get_stt)]
TeacherDep = Annotated[Teacher, Depends(get_teacher)]
