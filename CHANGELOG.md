# Changelog

All notable changes to QuizDeck are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-30

### Added

- Text-to-speech (OpenRouter `/api/v1/audio/speech`): per-user toggle speaks the
  study question and the teacher explanation aloud from speaker buttons in the
  study view; admin can disable TTS globally (`tts_allowed`).
- Vocal-ready pass: optional extra LLM rewrite (`question_vocal`, `teacher_vocal`)
  turns question/explanation into plain spoken sentences before synthesis, using
  `VOCAL_MODEL` (defaults to `TEACHER_MODEL`).
- Shared OpenRouter configuration: `OPENROUTER_BASE_URL` and `OPENROUTER_API_KEY`
  are now the fallback for every `X_BASE_URL` / `X_API_KEY` (judge, STT, teacher,
  TTS).
