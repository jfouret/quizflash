from fastapi import APIRouter, Response, status

from app import crud
from app.dependencies import SessionDep
from app.schemas import TagRead

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=list[TagRead])
def list_tags(session: SessionDep) -> list[TagRead]:
    return [TagRead.model_validate(tag) for tag in crud.list_tags(session)]


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(tag_id: int, session: SessionDep) -> Response:
    crud.delete_tag(session, tag_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
