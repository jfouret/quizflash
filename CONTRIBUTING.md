# Contributing

Thanks for taking the time to improve QuizDeck. This page covers the practical
steps; the release rules live in [`docs/release.md`](docs/release.md).

## Set up

```bash
uv sync
uv run python -m app.cli create-admin --email admin@example.com
uv run uvicorn app.main:app --reload
```

Python 3.12 or newer. `ffmpeg` is needed for voice answers.

The stylesheet `app/static/style.css` is generated from
`app/static/css/input.css` and committed, so a plain `uvicorn` run serves the
real thing. After changing `input.css` or any template class, rebuild it:

```bash
scripts/build-css.sh
```

The script downloads a checksum-pinned Tailwind CLI release into
`~/.cache/quizdeck` (no Node.js needed) and writes the minified stylesheet. CI
re-runs it and fails if the committed file is stale.

## Before you open a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

`docker build --target test .` runs the same four checks inside the production
image (same Python, same dependencies, same ffmpeg), which is what CI does.

## Pull requests

- One topic per pull request, with a short description of the problem and the fix.
- Bump the version in `pyproject.toml` and add a `CHANGELOG.md` section when you
  touch `app/`, `Dockerfile` or `pyproject.toml`. Patch for a fix, minor for a
  feature, major for a breaking change.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`fix(auth): ...`, `feat(study): ...`, `docs: ...`).
- New behaviour needs a test. Security-relevant behaviour belongs in
  `tests/test_security.py`.
- `main` is protected: pull requests are required, history is linear, and commits
  must be signed. Squash or rebase when merging. Repository admins can merge without
  a review with `gh pr merge --admin`.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's private vulnerability reporting, as
described in [`SECURITY.md`](SECURITY.md).

## Licence

QuizDeck is distributed under the European Union Public Licence v. 1.2
(`EUPL-1.2`). By contributing you agree that your contribution is licensed under
the same terms.
