from collections.abc import Iterator
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class TTSResult(BaseModel):
    model_config = ConfigDict(strict=True)

    audio: bytes = Field(min_length=1)
    content_type: str = Field(min_length=1)


class TTSProvider(Protocol):
    model: str

    def speak(self, text: str, language: str) -> TTSResult: ...

    def speak_stream(self, text: str, language: str) -> Iterator[bytes]: ...


class TTSError(RuntimeError):
    pass
