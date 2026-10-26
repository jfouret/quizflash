from fastapi import APIRouter

from app import crud
from app.dependencies import SessionDep
from app.schemas import SettingsRead, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def read_settings(session: SessionDep) -> SettingsRead:
    return SettingsRead.model_validate(crud.get_settings(session))


@router.patch("", response_model=SettingsRead)
def patch_settings(data: SettingsUpdate, session: SessionDep) -> SettingsRead:
    return SettingsRead.model_validate(crud.update_settings(session, data))
