# CLAUDE.md -- navigation for Claude Code

> This file is a **router**. It holds only what is needed on every request.
> Everything else lives in [`docs/`](docs/) and [`.claude/`](.claude/).

## Project context (one line)

`mikrot` is a small Python 3.12 CLI for managing a **MikroTik** router
over its **REST API** (httpx + HTTP Basic).

## Hard rules (always apply)

- **Language:** code, identifiers, and comments in `src/` and `tests/` are English.
- **ASCII-only in `src/` and `tests/`** (enforced by ruff `RUF`).
- **Platform:** the project is cross-platform. Windows + PowerShell 7 (Core) is just one of the supported setups; command examples in this file use PowerShell syntax.
- **Settings come only from `.env`**, all variables prefixed `MIKROT_` (via `pydantic-settings`). There is no YAML layer. `MIKROT_PASSWORD` is required. See [`docs/decisions.md`](docs/decisions.md) DEC-003.
- **AI-friendly -- lightweight set** (intentional, the project is small): `--json`, errors-as-data (`code`/`fix`/`fix_description`), renderer split Rich/JSON, `mikrot manifest --json`. **No** `schema`, synthetic envelopes, drift tests, or heavy contract machinery. See DEC-002.
- **Exit codes are meaningful** (1 connect / 2 HTTP / 3 not-found / 4 ambiguous), not always 0. `doctor` returns exit 0 (errors-as-data), `--strict` -> 1. See DEC-005.
- **`make-static` / `make-dynamic` are router mutations.** Dry-run by default; `--commit` applies. Live tests are **read-only by default**; run `make*` only on explicit request.

## Where to look for details

| Topic | File |
| --- | --- |
| Requirements + MikroTik REST heuristics (**source of truth**) | [`docs/requirements.md`](docs/requirements.md) |
| Accepted decisions (ADR) | [`docs/decisions.md`](docs/decisions.md) |
| Install / usage / examples | [`README.md`](README.md) |

## Repository layout

```
src/mikrot/
  app.py            # Typer root + --json hoisting + main()
  context.py        # CliContext (renderer + lazy settings) + emit_errors
  output.py         # Renderer ABC + RichRenderer / JsonRenderer
  errors.py         # MikrotError (code/fix/fix_description/context, exit_code)
  settings.py       # pydantic-settings (env_prefix MIKROT_) + load_settings
  rest.py           # httpx client + json_safe (utf-8/cp1251) + get_one + request->MikrotError
  diagnostics.py    # CheckResult / DoctorEnvelope / compute_overall_status
  models.py         # LeaseActionEnvelope
  commands/         # doctor.py, dhcp.py, lease.py (make-static/dynamic), manifest.py
tests/              # pytest (httpx mocked; no live router needed)
docs/               # requirements, decisions (source of truth)
.claude/            # Claude local working files (memory/scratch not committed)
.env                # router credentials (gitignored)
pyproject.toml      # single UV package, hatchling
```

## Entry point for AI agents

```pwsh
mikrot manifest --json
```

Returns `version`, `contract_version`, `commands[]` (with `response_shape` + `error_codes`)
and `infrastructure_errors`. Source -- [`src/mikrot/commands/manifest.py`](src/mikrot/commands/manifest.py).

## Useful commands

```pwsh
uv sync --extra dev          # dependencies (including dev)
uv run pytest                # tests (no live router)
uv run ruff check .          # lint
uv run mypy src              # types
uv run mikrot doctor         # live check against the router from .env
uv run mikrot --json manifest
```
