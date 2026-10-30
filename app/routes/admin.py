from fastapi import APIRouter, Response, status

from app import crud
from app.dependencies import AdminUser, AuthConfigDep, SessionDep
from app.schemas import (
    AppSettingsRead,
    AppSettingsUpdate,
    DeckRead,
    UserAdminUpdate,
    UserRead,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserRead])
def list_users(session: SessionDep, _: AdminUser) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in crud.list_users(session)]


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    data: UserAdminUpdate,
    session: SessionDep,
    admin: AdminUser,
    config: AuthConfigDep,
) -> UserRead:
    return UserRead.model_validate(
        crud.admin_update_user(
            session,
            admin,
            user_id,
            status=data.status,
            role=data.role,
            oidc_enabled=config.oidc_enabled,
        )
    )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, session: SessionDep, admin: AdminUser) -> Response:
    crud.delete_user(session, admin, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/settings", response_model=AppSettingsRead)
def read_app_settings(session: SessionDep, _: AdminUser) -> AppSettingsRead:
    return AppSettingsRead.model_validate(crud.get_app_settings(session))


@router.patch("/settings", response_model=AppSettingsRead)
def patch_app_settings(
    data: AppSettingsUpdate, session: SessionDep, _: AdminUser
) -> AppSettingsRead:
    return AppSettingsRead.model_validate(crud.update_app_settings(session, data))


@router.post("/decks/{deck_id}/unpublish", response_model=DeckRead)
def unpublish_deck(deck_id: int, session: SessionDep, _: AdminUser) -> DeckRead:
    return DeckRead.model_validate(crud.unpublish_deck(session, deck_id))
