from fastapi import APIRouter, Response, status

from app import crud
from app.dependencies import SessionDep
from app.schemas import CardCreate, CardRead, CardUpdate

router = APIRouter(prefix="/api/cards", tags=["cards"])


@router.get("", response_model=list[CardRead])
def list_cards(
    session: SessionDep, deck_id: int | None = None, tag: str | None = None
) -> list[CardRead]:
    return [CardRead.model_validate(card) for card in crud.list_cards(session, deck_id, tag)]


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
def create_card(data: CardCreate, session: SessionDep) -> CardRead:
    return CardRead.model_validate(crud.create_card(session, data))


@router.get("/{card_id}", response_model=CardRead)
def get_card(card_id: int, session: SessionDep) -> CardRead:
    return CardRead.model_validate(crud.get_card(session, card_id))


@router.patch("/{card_id}", response_model=CardRead)
def update_card(card_id: int, data: CardUpdate, session: SessionDep) -> CardRead:
    return CardRead.model_validate(crud.update_card(session, card_id, data))


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: int, session: SessionDep) -> Response:
    crud.delete_card(session, card_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
