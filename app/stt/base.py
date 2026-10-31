import json
import math
import re
import subprocess
import tempfile
from typing import Any, Protocol

from pydantic import BaseModel


class STTResult(BaseModel):
    text: str
    audio_duration_ms: int
    stt_duration_ms: int = 0


class STTProvider(Protocol):
    def transcribe(self, audio: bytes, language: str) -> STTResult: ...


class STTError(RuntimeError):
    pass


# Uploaded audio is untrusted: only local files in known audio containers may be parsed.
ALLOWED_FORMATS = "matroska,webm,mov,mp4,m4a,ogg,wav,mp3"
INPUT_FLAGS = [
    "-protocol_whitelist",
    "file",
    "-format_whitelist",
    ALLOWED_FORMATS,
]


def measure_audio_duration(audio: bytes) -> int:
    """Measure duration from the uploaded container, including browser WebM audio."""
    if not audio:
        raise STTError("Audio file is empty")
    with tempfile.NamedTemporaryFile(suffix=".audio") as audio_file:
        audio_file.write(audio)
        audio_file.flush()
        duration = _ffprobe_duration(audio_file.name)
        if duration is None:
            duration = _ffmpeg_duration(audio_file.name)
    if duration is None or not math.isfinite(duration) or duration <= 0:
        raise STTError("Could not measure audio duration; upload valid audio")
    return round(duration * 1000)


def _ffprobe_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                *INPUT_FLAGS,
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        payload: dict[str, Any] = json.loads(result.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _ffmpeg_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostdin", *INPUT_FLAGS, "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    matches = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not matches:
        return None
    hours, minutes, seconds = matches[-1]
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
