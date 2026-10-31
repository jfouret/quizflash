"""QuizDeck application package."""

import os
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

load_dotenv()

try:
    # Single source of truth: the version declared in pyproject.toml.
    __version__ = version("quizdeck")
except PackageNotFoundError:  # source tree without an installed distribution
    __version__ = "0.0.0+unknown"

# Set by the image build (for example 0.3.0-2026-10-31); empty in a source checkout.
__build_tag__ = os.getenv("BUILD_TAG", "")
