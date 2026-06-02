# Requirements -- `mikrot`

> Consolidated requirements and the project's source of truth. Self-contained: the
> MikroTik REST behaviour the tool depends on is described inline.

## 1. Purpose

`mikrot` is a small CLI for administering a **MikroTik** router through its **REST API**
(RouterOS 7.1+). It is a standalone, single-package tool with a focused command set
around DHCP leases plus connection diagnostics:

- `doctor` -- preflight checks + baseline router info
- `dhcp-leases` -- list DHCP server leases with filters
- `make-static` -- convert a dynamic lease into a static reservation
- `make-dynamic` -- convert a static reservation back into a dynamic lease
- `manifest` -- machine-readable self-description for AI/script consumers

## 2. Platform and stack

The tool is **cross-platform**. It is developed and tested on Windows with PowerShell 7;
the code targets any platform with Python 3.12.

| Aspect | Choice |
| --- | --- |
| Language | Python 3.12 |
| Packaging | UV + hatchling, one package `src/mikrot` (no separate library/service) |
| CLI | Typer + Rich |
| HTTP | httpx (HTTP Basic auth) |
| Configuration | pydantic-settings (`.env`, prefix `MIKROT_`) |
| Code conventions | code, identifiers and in-code comments in English, ASCII-only (lint-enforced) |
| Documentation | English |
| Quality gates | pytest, ruff, mypy |

## 3. Commands

Every command supports two output modes: Rich (default) and `--json` (a global flag
accepted both before and after the subcommand).

### 3.1. `mikrot doctor [--strict]`

Connection diagnostics as a set of checks (rows `ok` / `warn` / `fail`) plus an
aggregate `overall_status` (priority `fail` > `warn` > `ok`). Checks:

1. `config_password_set` -- is `MIKROT_PASSWORD` set.
2. `router_reachable` -- TCP/HTTP reachability (any HTTP response, including 401, counts
   as reachable; only a transport error is a `fail`).
3. `rest_api_responds` -- `GET /system/identity` returns 200 and parses as JSON.

If the router is reachable, a **baseline info** block follows: `/system/identity`,
`/system/resource` (subset of keys), `/system/routerboard` (subset of keys). If it is
unreachable, the baseline is skipped without error.

`doctor` is **errors-as-data**: it exits 0 on any outcome by default; `--strict` makes
it exit 1 when `overall_status != "ok"`.

### 3.2. `mikrot dhcp-leases [--mac SUB] [--name SUB] [--status S]`

Leases from `/ip/dhcp-server/lease`. Filters: MAC substring (case-insensitive),
host-name substring, exact `status`. Sort: `status` ascending, then IP ascending.

- Rich: a 10-column table (`address | active-address | mac-address | host-name |
  status | dynamic | expires-after | last-seen | server | comment`); `waiting` rows are
  dimmed.
- `--json`: an array of the **full** lease objects (~19 fields), not the column subset.

The MAC substring filter is handy for grouping devices by vendor prefix (OUI).

### 3.3. `mikrot make-static <ip> [--commit]`

Convert a dynamic lease into a static reservation. Lookup by exact `address == ip`. By
default a **dry-run** (show the plan, change nothing); `--commit` issues
`POST /ip/dhcp-server/lease/make-static {"numbers": "<.id>"}`. Idempotent: on an
already-static lease (`dynamic=false`) it is a no-op.

### 3.4. `mikrot make-dynamic <ip> [--commit]`

The reverse operation. RouterOS REST exposes **no** `make-dynamic` action (and a PATCH
of the `dynamic` field is rejected), so this is implemented as
`DELETE /ip/dhcp-server/lease/<.id>`. A client with an active bound lease keeps its IP
until the lease timer expires, then receives a fresh dynamic lease on DHCP renew. Dry-run
by default; `--commit` applies. On an already-dynamic lease (`dynamic=true`) it is a
no-op.

### 3.5. `mikrot manifest [--compact]`

Machine-readable self-description for AI consumers (see p. 5). Used with the global
`--json` flag.

## 4. Configuration (`.env`, prefix `MIKROT_`)

Configuration is read via `pydantic-settings`. Two `.env` files are merged into the
environment, both loaded with `override=False` (shell variables always win):

1. a **project-local** `.env`, discovered by walking up from the current directory;
2. a **global** `.env` at `~/.config/mikrot/.env` (the directory is the same on every
   OS; override it with `MIKROT_CONFIG_HOME`, read from the shell environment).

The project-local file is loaded **before** the global one, so a local `.env` wins over
the global file. The global file is **auto-created on first run** as a fully commented
scaffold (every variable present but commented out, so it sets nothing until edited); an
existing file is never overwritten, and filesystem errors while creating it are ignored
(read-only commands must not abort). There is no YAML layer.

| Variable | Type | Example | Required |
| --- | --- | --- | --- |
| `MIKROT_HOST` | str | `192.168.88.1` | no |
| `MIKROT_PORT` | int | `80` | no |
| `MIKROT_SCHEME` | str | `http` | no |
| `MIKROT_USER` | str | `admin` | no |
| `MIKROT_PASSWORD` | str | -- | **yes** (empty -> `config_missing`) |
| `MIKROT_TIMEOUT` | float | `5.0` | no |

`base_url` = `{scheme}://{host}:{port}/rest`. Precedence (higher wins): constructor
arguments > shell environment > project-local `.env` > global `.env` > built-in defaults.
The example values target a
factory-fresh MikroTik (its default LAN address and `admin` user); set the real values
in `.env` (copy `.env.example`). Only `MIKROT_PASSWORD` is mandatory: it is required at
use time (`load_settings`), but `doctor` builds settings tolerantly and reports a missing
password as a `fail` row instead of crashing.

## 5. AI-friendly layer (lightweight)

Deliberately lightweight, because the project is small and simple for an AI to drive.
What **is** present:

- **Global `--json`** -- one JSON document per call; flexible flag position (hoisted in
  `main()`); non-ASCII preserved (Cyrillic survives the round-trip).
- **errors-as-data** -- an envelope with a stable `code`, plus `fix` (a literal
  `mikrot ...` command or `null`) and `fix_description` (free text); both keys are always
  present; `context` is merged on top (for example `ip`).
- **renderer-split** -- a `Renderer` interface + `RichRenderer` / `JsonRenderer`;
  commands never print directly.
- **`mikrot manifest --json`** -- `version`, `contract_version` (int), `commands[]`, a
  `models` map, `error_shape`, `infrastructure_errors[]`, and an `exit_codes` map
  (`code -> exit`). Built by hand (a dict literal), without command-tree introspection.
  Each command carries a
  `response_shape {kind, model, fields}`, where `fields` is a `{name -> type}` map (a
  `passthrough` flag marks raw RouterOS objects whose field set varies, e.g. leases).
  `error_shape` describes the fixed errors-as-data envelope; nested models referenced as
  `array<Model>` are documented in the `models` map.

**Error codes.** A command's `error_codes` lists only its **domain-specific** codes; the
top-level `infrastructure_errors` (`router_unreachable`, `http_error`, `config_missing`,
`unknown`) apply to any command that contacts the router or loads settings. A consumer
takes the union.

**Versioning.** `contract_version` is a plain int, bumped on ANY change to the published
contract (command set, response/error shapes, or code sets) so pinned agents get a signal.

Deliberately **NOT** done (too heavy for this project's scale): a `schema` command, a
synthetic-envelope model registry, heavy contract-drift machinery. The only guards are
light tests: every manifest code is a registered code, per-command codes stay domain-only,
and the hand-written `fields` match the Pydantic `model_fields`.

**Why.** The AI-friendly layer was requested "as lightweight as possible." A deliberate
trade favouring code simplicity over reference completeness. See DEC-002 and DEC-011.

**How to apply.** When adding a command, add its entry (with `response_shape.fields`) to
the manifest by hand, list only domain codes in `error_codes`, and bump `contract_version`.
The light consistency test keeps `fields` honest. Do not pull in heavyweight contract
machinery without an explicit request.

### Exit codes (open -- tracked separately in the backlog)

The tool keeps **meaningful exit codes** rather than always returning 0:
`router_unreachable`=1, `http_error`=2, `lease_not_found`=3, `lease_ambiguous`=4,
`config_missing`=1, `unknown`=1. The mapping is a single source in one place (the errors
module). The structured error carries the `code`; the shared error handler renders the
envelope and exits with the mapped code.

**Why.** A hybrid: a structured, machine-readable error in the output (errors-as-data)
**and** a meaningful return code for shell scripts.

**How to apply.** `doctor` is the exception -- always exit 0 (errors-as-data in rows),
`--strict` -> exit 1 when `overall_status != "ok"`. The code mapping is load-bearing; do
not renumber it.

## 6. MikroTik REST -- principles and heuristics

> Verified against RouterOS 7.x hardware.

### 6.1. REST in general

- Endpoint: `http://<host>:<port>/rest/<menu-path>`. Auth is HTTP Basic. HTTP/80 without
  HTTPS works when the router's `www` service is enabled.
- Single-object menus (`/system/identity`, `/system/resource`, `/system/routerboard`)
  inconsistently return either a dict or a one-item list -- the client normalises both
  forms.
- **CRUD vs action asymmetry.** `POST /rest/ip/dhcp-server/lease/make-static
  {"numbers": "<.id>"}` exists; the paired `make-dynamic` does not
  (`HTTP 400 "no such command"`); `PATCH {"dynamic": ...}` is rejected
  (`unknown parameter dynamic` -- it is a managed field). The universal workaround for a
  missing action is `DELETE /rest/<menu>/<.id>`.
- **Action endpoints require the `policy` permission flag** in the router user's group.
  `read + write + rest-api` is not enough for `make-static`
  (`HTTP 500 / not enough permissions`); read-only GETs work without it.
- **Passing `.id`:** CRUD (DELETE/PATCH) -- in the URL path; action (POST) -- in the body
  as `{"numbers": "<.id>"}`.

### 6.2. Encodings

- **Input.** Host-names/comments arrive as-is from DHCP clients; legacy Russian Windows
  sends cp1251, which makes a naive JSON decode fail with `UnicodeDecodeError`. The fix
  is a cascading decoder: utf-8 -> cp1251 -> last-resort lossy replace. Cyrillic stays
  readable.
- **Output.** On Windows, stdout defaults to an OEM codepage, which would mangle correct
  Cyrillic. The fix is to reconfigure stdout to UTF-8 before the Rich console is
  initialised. Bonus: Rich then switches from ASCII frames to Unicode box-drawing.

### 6.3. The DHCP lease table as the MAC->IP source of truth

- `/ip/dhcp-server/lease` is sufficient (no ARP needed when clients always DHCP through
  this router).
- Current IP for a MAC = `lease["active-address"]` or, as a fallback, `lease["address"]`.
  On `waiting` leases the `active-*` fields are **absent as keys** -- the fallback to
  `address` is mandatory.
- **Liveness != presence of a record.** A device is live iff `status == "bound"`. The
  table accumulates `waiting` records for years (entries idle for several years have been
  observed).
- `dynamic == "false"` is an admin-registered reservation; `"true"` is a dynamic lease
  from the pool.
- `comment` is a human label set by the router admin -- a potentially valuable context
  channel for an AI.

## 7. Error codes and exit codes

The error envelope carries a `code`; each code maps to a process exit code.

| `code` | exit | level | when |
| --- | --- | --- | --- |
| `router_unreachable` | 1 | infrastructure | connect/timeout to the router |
| `http_error` | 2 | infrastructure | router answered with an HTTP error (incl. lack of permissions) |
| `lease_not_found` | 3 | command | `make-*`: no lease with that IP |
| `lease_ambiguous` | 4 | command | `make-*`: more than one lease with that IP |
| `config_missing` | 1 | infrastructure | `MIKROT_PASSWORD` not set |
| `unknown` | 1 | infrastructure | uncategorised path |

`doctor` is excluded from this scheme: it always exits 0 (errors-as-data), `--strict` ->
1.

This `code -> exit` mapping is also published machine-readably in `mikrot manifest` as
the `exit_codes` map (single source: the errors module). See DEC-005 and DEC-011.

## 8. Architecture (modules)

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
```

Key principles:

- Commands (`commands/*.py`) never print directly -- only through the active renderer.
- httpx transport errors are mapped to the error envelope in **one place** (the REST
  request helper); command bodies are wrapped by a shared error handler (render + exit
  code).
- Settings are lazy: `--help` / `--version` / `manifest` work without `MIKROT_PASSWORD`.
- The pure lease-selection logic is separated from the network fetch, so it is unit-tested
  without a network.

## 9. Out of scope / possible future work

- **[L]** HTTPS + certificate verification (a `MIKROT_VERIFY_TLS` setting) -- currently
  `http` only.
- **[L]** Additional RouterOS menus (`/interface`, `/ip/address`, ...) -- as the need
  arises.
- **[L]** Caching leases between calls -- not needed (on-demand).
- **[L]** Grouping commands by resource (`mikrot lease make-static`) -- if the command
  count grows noticeably.
