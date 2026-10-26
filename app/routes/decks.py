from fastapi import APIRouter, Response, status

from app import crud
from app.dependencies import SessionDep
from app.schemas import DeckCreate, DeckRead, DeckUpdate

router = APIRouter(prefix="/api/decks", tags=["decks"])


@router.get("", response_model=list[DeckRead])
def list_decks(session: SessionDep) -> list[DeckRead]:
    return [DeckRead.model_validate(deck) for deck in crud.list_decks(session)]


@router.post("", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(data: DeckCreate, session: SessionDep) -> DeckRead:
    return DeckRead.model_validate(crud.create_deck(session, data))


@router.get("/{deck_id}", response_model=DeckRead)
def get_deck(deck_id: int, session: SessionDep) -> DeckRead:
    return DeckRead.model_validate(crud.get_deck(session, deck_id))


@router.patch("/{deck_id}", response_model=DeckRead)
def update_deck(deck_id: int, data: DeckUpdate, session: SessionDep) -> DeckRead:
    return DeckRead.model_validate(crud.update_deck(session, deck_id, data))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, session: SessionDep) -> Response:
    crud.delete_deck(session, deck_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
