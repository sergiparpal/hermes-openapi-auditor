# Claude Code session notes for this repository

These are durable constraints for Claude Code sessions on
`hermes-openapi-auditor`. Read them before editing.

## Always

- Run `.venv/bin/pytest` before declaring any change done; the full suite
  is fast (~2s).
- Run `.venv/bin/ruff check .` and `.venv/bin/ruff format --check .` after
  any edit to Python files.
- Run `.venv/bin/mypy auditor/` after touching anything in `auditor/`. The
  rule "mypy --strict clean" applies to the whole `auditor/` package.
- Follow PEP 8 and full type hints on public functions. `from __future__
  import annotations` at the top of every module.
- Keep `tools.py` thin: it translates the Hermes handler protocol to the
  internal `auditor.runner` API. Business logic goes in `auditor/`.

## Never

- Do **not** run `claude init` — it would overwrite this file. The session
  context for this repo lives here.
- Do **not** modify Hermes core (`run_agent.py`, `cli.py`,
  `gateway/run.py`, `hermes_cli/main.py`, etc.). If a plugin capability
  is needed that Hermes doesn't expose, file an upstream issue rather
  than working around it.
- Do **not** add fields to `plugin.yaml` that aren't in the official
  manifest schema (no `category`, `license`, `homepage`, or
  `dependencies` — they were investigated in the plan revision and
  confirmed not to exist).
- Do **not** make the `audit_openapi_spec` handler raise — per Hermes
  contract it must return a JSON string in every code path (errors
  included).
- Do **not** add `__init__.py` to the repo root *without* deferring its
  relative imports into `register()`. The directory name has a hyphen,
  so eager `from .` imports fail in pytest collection (and likely other
  bare-import contexts).

## Layout reminders

- The package is importable as `hermes_openapi_auditor` (underscores),
  mapped to the repo root via `pyproject.toml`'s `package-dir`.
- The plugin directory name is `hermes-openapi-auditor` (hyphens) because
  Hermes uses the directory name as the plugin name.
- Tests use `--import-mode=importlib` (see `[tool.pytest.ini_options]`)
  so the hyphenated directory doesn't break test collection.

## Running things

```bash
.venv/bin/pytest                            # full suite
.venv/bin/pytest --cov=auditor              # with coverage
.venv/bin/ruff check .                      # lint
.venv/bin/ruff format .                     # apply formatting
.venv/bin/mypy auditor/                     # type-check
```

## Hermes target version

v0.14.0 (release tag `v2026.5.16`). Pin against that when in doubt.
