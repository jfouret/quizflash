from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class TTSResult(BaseModel):
    model_config = ConfigDict(strict=True)

    audio: bytes = Field(min_length=1)
    content_type: str = Field(min_length=1)


@dataclass
class TTSStream:
    """Audio chunks whose provider answer is already validated.

    The provider call and its first chunk happen before this object exists, so a
    failure raises TTSError while the caller can still answer with an error
    status instead of a 200 whose body no browser can decode.
    """

    content_type: str
    chunks: Iterator[bytes]


class TTSProvider(Protocol):
    model: str

    def speak(self, text: str, language: str) -> TTSResult: ...

    def speak_stream(self, text: str, language: str) -> TTSStream: ...


class TTSError(RuntimeError):
    pass
