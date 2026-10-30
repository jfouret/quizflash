from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class TTSResult(BaseModel):
    model_config = ConfigDict(strict=True)

    audio: bytes = Field(min_length=1)
    content_type: str = Field(min_length=1)


class TTSProvider(Protocol):
    model: str

    def speak(self, text: str, language: str) -> TTSResult: ...


class TTSError(RuntimeError):
    pass
