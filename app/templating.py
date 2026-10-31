from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import __build_tag__, __version__

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Cache-busting suffix for static assets, so browsers pick up new JS after an upgrade.
templates.env.globals["asset_version"] = __version__
templates.env.globals["app_version"] = __version__
templates.env.globals["build_tag"] = __build_tag__

# Fixed messages shown after a redirect (`?notice=<key>`); never echo user input.
NOTICES = {
    "deck-created": "Deck created.",
    "deck-saved": "Deck saved.",
    "deck-deleted": "Deck deleted.",
    "deck-followed": "You now follow this deck. Its cards are in your study queue.",
    "deck-unfollowed": "Deck unfollowed.",
    "deck-copied": "Deck copied. This copy is yours to edit.",
    "card-created": "Card added.",
    "card-saved": "Card saved.",
    "card-deleted": "Card deleted.",
    "history-cleared": "History cleared.",
    "settings-saved": "Settings saved.",
    "token-revoked": "Token revoked.",
    "user-updated": "User updated.",
    "user-deleted": "User deleted.",
    "app-settings-saved": "Application settings saved.",
    "agent-saved": "Agent settings saved.",
    "deck-unpublished": "Deck unpublished.",
}
templates.env.globals["notices"] = NOTICES
