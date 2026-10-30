from fastapi import APIRouter, Response, status

from app import auth, crud
from app.dependencies import CurrentUser, SessionDep
from app.schemas import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    SettingsRead,
    SettingsUpdate,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsRead)
def read_settings(session: SessionDep, user: CurrentUser) -> SettingsRead:
    return SettingsRead.model_validate(crud.get_settings(session, user))


@router.patch("", response_model=SettingsRead)
def patch_settings(data: SettingsUpdate, session: SessionDep, user: CurrentUser) -> SettingsRead:
    return SettingsRead.model_validate(crud.update_settings(session, user, data))


@router.get("/tokens", response_model=list[ApiTokenRead])
def list_tokens(session: SessionDep, user: CurrentUser) -> list[ApiTokenRead]:
    return [ApiTokenRead.model_validate(token) for token in auth.list_api_tokens(session, user)]


@router.post("/tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(data: ApiTokenCreate, session: SessionDep, user: CurrentUser) -> ApiTokenCreated:
    token, raw = auth.create_api_token(session, user, data.name)
    return ApiTokenCreated(**ApiTokenRead.model_validate(token).model_dump(), token=raw)


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(token_id: int, session: SessionDep, user: CurrentUser) -> Response:
    try:
        auth.revoke_api_token(session, user, token_id)
    except LookupError as exc:
        raise crud.NotFoundError(str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
