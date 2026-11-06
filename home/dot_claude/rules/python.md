---
paths: ["**/*.py", "**/pyproject.toml", "**/uv.lock", "**/requirements*.txt"]
---
# Python — use uv, never pip

Use `uv` for all Python projects — never `pip` (a repo's own CLAUDE.md/tooling wins if it says otherwise):

- Never `pip`: no `pip install`, `pip freeze`, or `python -m pip`. Use the `uv` equivalents.
- Dependencies: add/remove with `uv add` / `uv remove`; install/sync from lockfile with
  `uv sync`. Keep `pyproject.toml` + `uv.lock` as the source of truth (no `requirements.txt`
  unless a project already uses one).
- Running code: `uv run <cmd>` instead of activating a venv and calling `python`/tools directly.
- New projects: scaffold with `uv init`; manage Python versions with `uv python`.
- Most repos here use ruff + pre-commit and pyright/basedpyright — run the repo's configured
  checks and respect its settings (line-length, rule sets, and Python target differ per repo;
  don't impose a global value).
