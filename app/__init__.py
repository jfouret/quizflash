"""QuizDeck application package."""

from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

load_dotenv()

try:
    # Single source of truth: the version declared in pyproject.toml.
    __version__ = version("quizdeck")
except PackageNotFoundError:  # source tree without an installed distribution
    __version__ = "0.0.0+unknown"
