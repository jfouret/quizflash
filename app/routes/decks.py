from fastapi import APIRouter, Response, status

from app import crud
from app.dependencies import CurrentUser, SessionDep
from app.schemas import DeckCreate, DeckRead, DeckUpdate, PublicDeckRead

router = APIRouter(prefix="/api/decks", tags=["decks"])
public_router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("", response_model=list[DeckRead])
def list_decks(session: SessionDep, user: CurrentUser) -> list[DeckRead]:
    return [DeckRead.model_validate(deck) for deck in crud.list_decks(session, user)]


@router.post("", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def create_deck(data: DeckCreate, session: SessionDep, user: CurrentUser) -> DeckRead:
    return DeckRead.model_validate(crud.create_deck(session, user, data))


@router.get("/{deck_id}", response_model=DeckRead)
def get_deck(deck_id: int, session: SessionDep, user: CurrentUser) -> DeckRead:
    return DeckRead.model_validate(crud.get_deck(session, user, deck_id))


@router.patch("/{deck_id}", response_model=DeckRead)
def update_deck(deck_id: int, data: DeckUpdate, session: SessionDep, user: CurrentUser) -> DeckRead:
    return DeckRead.model_validate(crud.update_deck(session, user, deck_id, data))


@router.delete("/{deck_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deck(deck_id: int, session: SessionDep, user: CurrentUser) -> Response:
    crud.delete_deck(session, user, deck_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{deck_id}/follow", response_model=DeckRead)
def follow_deck(deck_id: int, session: SessionDep, user: CurrentUser) -> DeckRead:
    return DeckRead.model_validate(crud.follow_deck(session, user, deck_id))


@router.delete("/{deck_id}/follow", status_code=status.HTTP_204_NO_CONTENT)
def unfollow_deck(deck_id: int, session: SessionDep, user: CurrentUser) -> Response:
    crud.unfollow_deck(session, user, deck_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{deck_id}/copy", response_model=DeckRead, status_code=status.HTTP_201_CREATED)
def copy_deck(deck_id: int, session: SessionDep, user: CurrentUser) -> DeckRead:
    return DeckRead.model_validate(crud.copy_deck(session, user, deck_id))


@public_router.get("/decks", response_model=list[PublicDeckRead])
def list_public_decks(session: SessionDep, user: CurrentUser) -> list[PublicDeckRead]:
    return [
        PublicDeckRead(
            **DeckRead.model_validate(deck).model_dump(),
            owner_name=owner_name,
            card_count=card_count,
            following=deck.id is not None and crud.is_following(session, user, deck.id),
        )
        for deck, owner_name, card_count in crud.list_public_decks(session)
    ]
