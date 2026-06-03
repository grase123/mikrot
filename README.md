# mikrot

**mikrot** is a small, cross-platform Python CLI for managing MikroTik (RouterOS) routers
through their REST API. It is built to be automation- and **AI-friendly**: every command
speaks `--json`, errors come back as structured data (stable codes with machine-actionable
fixes), and `mikrot manifest` publishes a machine-readable self-description (commands,
response shapes, error and exit codes). That lets scripts, CI pipelines, and AI agents
drive it reliably -- while it stays an ergonomic CLI for people.

Standalone, single-package tool (RouterOS 7.1+). Stack: Python 3.12, UV, Typer, Rich,
httpx, Pydantic. The project is **small and simple**, so the AI-friendly features are
provided in a **lightweight** form.

## What it does

| Command | Purpose |
| --- | --- |
| `mikrot doctor` | Connection diagnostics (ok/warn/fail + `overall_status`) + baseline router info (identity / resource / routerboard). |
| `mikrot dhcp-leases` | List DHCP leases (`/ip/dhcp-server/lease`) with `--mac` (= `-m`) / `--name` (= `--host`/`-n`) / `--status` (= `-s`) / `--comment` (= `-c`) / `--address` (= `--ip`/`-a`/`-i`) filters (repeatable: OR within an option). Aliases: `l`, `d`. |
| `mikrot make-static <ip>` | Convert a dynamic lease into a static reservation (dry-run by default; `--commit` applies). |
| `mikrot make-dynamic <ip>` | The reverse operation via `DELETE` (dry-run by default; `--commit` applies). |
| `mikrot manifest` | Machine-readable self-description of the CLI for AI (`--json`). |

## Installation

mikrot is built and run with [UV](https://docs.astral.sh/uv/). Install UV first (it is the
only prerequisite -- it manages the Python toolchain itself):

```pwsh
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
# macOS / Linux (bash/zsh)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart the terminal afterwards so `uv` is on `PATH`. See the
[UV install docs](https://docs.astral.sh/uv/getting-started/installation/) for alternatives
(Homebrew, pipx, standalone installers). Then install mikrot:

```pwsh
# Production install (CLI into the OS home):
uv tool install git+https://github.com/grase123/mikrot
uv tool update-shell                 # once; then restart the terminal
mikrot --version

# Dev (from the repository):
git clone https://github.com/grase123/mikrot.git
cd mikrot
uv sync --extra dev                  # venv for tests/lint and `uv run`
uv run mikrot --version

# Run `mikrot` directly (no `uv run`) -- editable OS-level install:
uv tool install --editable .         # links the source; picks up your edits
uv tool update-shell                 # once; then restart the terminal
mikrot --version
```

### Settings from the cloned repo

mikrot finds the nearest `.env` by walking up from the current directory. Create the repo's
`.env` once:

```pwsh
# Windows (PowerShell)
Copy-Item .env.example .env          # then set MIKROT_PASSWORD
```

```bash
# macOS / Linux (bash/zsh)
cp .env.example .env                 # then set MIKROT_PASSWORD
```

Any `mikrot` run from inside the cloned repo (or a subdirectory) then uses that `.env` --
even with the OS-level install, because discovery is based on the working directory, not on
where the tool is installed. Run it from elsewhere and it falls back to the global
`~/.config/mikrot/.env` and the shell environment (see [Configuration](#configuration)).

## Configuration

Settings come from environment variables prefixed `MIKROT_`, loaded via
`pydantic-settings`. There is no YAML layer. mikrot reads two `.env` files and
merges them with the shell environment.

### Where settings come from (precedence)

Higher wins:

1. **Shell environment** -- `MIKROT_*` variables already set in your shell (or by
   CI / a container / a secrets tool). These always win.
2. **Project-local `.env`** -- the nearest `.env` found by walking up from the
   current directory. Use this for per-project overrides.
3. **Global `.env`** -- `~/.config/mikrot/.env` (see below). Use this for your
   personal, machine-wide defaults.
4. **Built-in defaults** -- the values in the table below.

Both `.env` files are loaded without overriding what is already set, so the shell
always beats the files and a project-local `.env` beats the global one.

### The global config file

On first run mikrot creates `~/.config/mikrot/.env` if it does not exist (the
directory is created too). It is written as a **fully commented scaffold**: every
variable is present but commented out, so it sets nothing until you edit it.
Uncomment and edit only the lines you want. An existing file is never overwritten,
and if the home directory is not writable the step is skipped silently.

- The path is `~/.config/mikrot/` on every OS (Linux, macOS, Windows).
- Override the directory with **`MIKROT_CONFIG_HOME`** -- the file is then
  `$MIKROT_CONFIG_HOME/.env`. It is read from the shell environment only (it
  decides where the files live) and is handy for tests, CI, or keeping config
  outside `$HOME`.

### Variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `MIKROT_HOST` | `192.168.88.1` | Router host |
| `MIKROT_PORT` | `80` | REST API port |
| `MIKROT_SCHEME` | `http` | `http` / `https` |
| `MIKROT_USER` | `admin` | Login (HTTP Basic) |
| `MIKROT_PASSWORD` | -- (**required**) | Password; without it any command to the router returns `code="config_missing"` |
| `MIKROT_TIMEOUT` | `5.0` | HTTP timeout, seconds |

Only `MIKROT_PASSWORD` is required -- set it in any of the layers above. Every
other variable is optional: leave it out to use the default. `mikrot doctor`
reports if `MIKROT_PASSWORD` is not set.

To set a variable directly in the shell (precedence layer 1, beats both `.env`
files) for the current session:

```pwsh
# Windows (PowerShell)
$env:MIKROT_PASSWORD = "secret"
```

```bash
# macOS / Linux (bash/zsh)
export MIKROT_PASSWORD=secret
```

To start from a template, copy the repo's example into a project-local `.env`:

```pwsh
# Windows (PowerShell)
Copy-Item .env.example .env          # then set MIKROT_PASSWORD
```

```bash
# macOS / Linux (bash/zsh)
cp .env.example .env                 # then set MIKROT_PASSWORD
```

### Secrets from 1Password (`op://` references)

Instead of a literal password, any `MIKROT_*` value may be a 1Password **secret
reference**:

```
MIKROT_PASSWORD=op://Vault/MikroTik/password
```

On startup mikrot resolves such references with the 1Password CLI (`op read`), so the
secret never lives in a file. Requirements:

- the `op` CLI is installed and on `PATH`;
- you are signed in -- interactively (1Password desktop app integration), or for
  headless/CI via a service-account token in `OP_SERVICE_ACCOUNT_TOKEN` (read by `op`).

Only reference-shaped values are touched; a literal value still works unchanged. If `op`
is missing or a reference cannot be resolved, the command fails with
`code="secret_resolution_failed"`.

More password managers can be added without code via the `SECRETREF_PROVIDERS` env var (a
JSON array of providers). A built-in `env://${VAR:-default}` reference resolves environment
variables in-process. See [`src/mikrot/secretref/README.md`](src/mikrot/secretref/README.md).

## Examples

```pwsh
mikrot doctor                            # preflight + baseline router info
mikrot doctor --strict                   # exit 1 if overall_status != ok

mikrot dhcp-leases                       # all leases (Rich table; waiting dimmed)
mikrot l --status bound                  # alias for dhcp-leases (also `d`)
mikrot dhcp-leases --mac DC:2C:6E        # MAC substring; ':' / '-' / no separator all match (e.g. vendor OUI)
mikrot dhcp-leases --comment printer     # filter by comment substring
mikrot dhcp-leases -a 192.168.88.50      # IP substring (matches address or active-address)
mikrot l -a 10.0.0.5 -a 10.0.0.7         # repeat an option: match ANY of several IPs (OR)
mikrot dhcp-leases --status bound        # online clients only
mikrot --json dhcp-leases                # full lease (~19 fields) per record

mikrot make-static 192.168.88.50         # dry-run: shows the plan, changes nothing
mikrot make-static 192.168.88.50 --commit      # apply
mikrot make-dynamic 192.168.88.50 --commit     # reverse (via DELETE)
```

> Tip against a wide Rich table being truncated: set `COLUMNS` wider --
> `$env:COLUMNS=250` (PowerShell) or `export COLUMNS=250` (bash/zsh).

## JSON output (`--json`) -- for AI/scripts

The global `--json` flag switches output to a single JSON document per call.
The flag position is flexible: `mikrot --json dhcp-leases` is equivalent to
`mikrot dhcp-leases --json`.

```pwsh
mikrot --json doctor          # {"checks": [...], "overall_status": "...", "baseline": {...}|null}
mikrot --json dhcp-leases     # array of full lease objects
mikrot --json make-static IP  # {"action","ip","lease_id","committed","changed","note","before","after"}
mikrot --json manifest        # full CLI self-description
```

**Errors are data too (errors-as-data).** A structured envelope with a stable `code`:

```json
{"error": "no DHCP lease found for address 1.2.3.4",
 "code": "lease_not_found", "fix": null, "fix_description": null, "ip": "1.2.3.4"}
```

`fix` is a literal `mikrot ...` command (or `null`); `fix_description` is free text for
cases where the fix is not a single command. Both keys are always present (may be `null`).

### Codes and exit codes

`mikrot` **preserves meaningful exit codes** (rather than always returning 0) so that
scripts can branch on the exit status:

| `code` | exit | When |
| --- | --- | --- |
| `router_unreachable` | 1 | Could not reach the router (connect/timeout) |
| `http_error` | 2 | Router answered with an HTTP error (including insufficient permissions) |
| `lease_not_found` | 3 | `make-*`: no lease with that IP |
| `lease_ambiguous` | 4 | `make-*`: several leases with that IP |
| `config_missing` | 1 | `MIKROT_PASSWORD` not set |

`mikrot doctor` is the exception: always **exit 0** (errors-as-data); `--strict` switches
it to exit 1 on `warn`/`fail`.

## AI-friendly self-description

`mikrot manifest --json` is a machine-readable description of the commands: for each one,
`response_shape` (`{kind, model}`) and `error_codes`; at the top level,
`infrastructure_errors` and `contract_version`. Lightweight set: no `schema`, synthetic
envelopes, drift tests, or heavy contract machinery.

## MikroTik REST specifics (important)

- Endpoint: `http://<host>:<port>/rest/<menu>`. Auth is HTTP Basic. The `www` service
  must be enabled on the router (`/ip service www`).
- Single-object menus (`/system/identity`, ...) sometimes return a dict, sometimes a
  one-item list -- the client normalizes both forms.
- **Encoding:** hostname/comment may arrive as cp1251 (legacy Windows clients); the
  decoder is cascading (utf-8 -> cp1251 -> lossy). Non-ASCII text is preserved.
- **REST asymmetry:** `make-static` exists as an action endpoint, but `make-dynamic`
  does **not** (RouterOS does not expose it; a PATCH of the `dynamic` field is rejected
  too). So "make dynamic" = `DELETE` of the static entry.
- **`make-*` require the `policy` flag on the router user** -- otherwise
  `HTTP 500 / not enough permissions`. Read-only GETs work without it.
- **Liveness:** a record in the DHCP table != the VM is alive. Alive <=> `status == "bound"`;
  `waiting` records accumulate for years.

Details and heuristics are in [`docs/requirements.md`](docs/requirements.md)
and [`docs/decisions.md`](docs/decisions.md).

## Documentation

- [`docs/requirements.md`](docs/requirements.md) -- requirements (source of truth).
- [`docs/decisions.md`](docs/decisions.md) -- accepted decisions (DEC-001..).

## Development

```pwsh
uv sync --extra dev          # dependencies
uv run pytest                # tests (no live router: httpx mocked)
uv run ruff check .          # lint
uv run mypy src              # types
uv run mikrot doctor         # live check against the router from .env
```

Code and identifiers are English (ASCII); documentation is English.
