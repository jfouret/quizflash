from typing import Annotated, cast

from fastapi import Depends, Request
from sqlmodel import Session

from app.database import get_session
from app.judge.base import Judge
from app.stt.base import STTProvider

SessionDep = Annotated[Session, Depends(get_session)]


def get_judge(request: Request) -> Judge:
    return cast(Judge, request.app.state.judge)


def get_stt(request: Request) -> STTProvider:
    return cast(STTProvider, request.app.state.stt)


JudgeDep = Annotated[Judge, Depends(get_judge)]
STTDep = Annotated[STTProvider, Depends(get_stt)]
