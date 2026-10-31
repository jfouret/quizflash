import hmac
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app import crud
from app.auth import AuthConfig, resolve_session
from app.database import get_session
from app.judge.base import Judge
from app.judge.openrouter import OpenRouterJudge
from app.models import User
from app.stt.base import STTProvider
from app.stt.openai_compat import OpenAICompatibleSTT
from app.teacher.base import Teacher
from app.teacher.openrouter import OpenRouterTeacher
from app.tts.base import TTSProvider
from app.tts.openrouter import OpenRouterTTS

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


def get_judge(request: Request, session: SessionDep) -> Judge:
    provider = request.app.state.judge
    if isinstance(provider, OpenRouterJudge):
        return OpenRouterJudge.from_config(crud.get_agent_config(session, "judge"))
    return cast(Judge, provider)


def get_stt(request: Request, session: SessionDep) -> STTProvider:
    provider = request.app.state.stt
    if isinstance(provider, OpenAICompatibleSTT):
        return OpenAICompatibleSTT.from_config(crud.get_agent_config(session, "stt"))
    return cast(STTProvider, provider)


def get_teacher(request: Request, session: SessionDep) -> Teacher:
    provider = request.app.state.teacher
    if isinstance(provider, OpenRouterTeacher):
        return OpenRouterTeacher.from_config(
            crud.get_agent_config(session, "teacher"),
            crud.get_agent_config(session, "verbalizer"),
        )
    return cast(Teacher, provider)


def get_tts(request: Request, session: SessionDep) -> TTSProvider:
    provider = request.app.state.tts
    if isinstance(provider, OpenRouterTTS):
        return OpenRouterTTS.from_config(crud.get_agent_config(session, "tts"))
    return cast(TTSProvider, provider)


JudgeDep = Annotated[Judge, Depends(get_judge)]
STTDep = Annotated[STTProvider, Depends(get_stt)]
TeacherDep = Annotated[Teacher, Depends(get_teacher)]
TTSDep = Annotated[TTSProvider, Depends(get_tts)]
