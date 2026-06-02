# Architecture Decisions (ADR) -- `mikrot`

> The source of truth for architecture decisions. Each is a `DEC-NNN`, recorded during
> the initial implementation (2026-06-01).

## DEC-001. Standalone, single-purpose tool with mutations in scope

**Context.** Managing MikroTik DHCP leases needs both read operations (listing,
diagnostics) and state-changing ones (promoting a lease to a static reservation and
back). A read-only tool would cover only half the job.

**Decision.** `mikrot` is a small, standalone, single-purpose CLI that deliberately
includes the mutating operations (`make-static` / `make-dynamic`), not just read-only
queries. To keep writes safe for unattended and agent use, they are gated behind a
dry-run default and an explicit `--commit` (see DEC-008), and they require the router
user to hold the `policy` permission flag.

## DEC-002. AI-friendly -- lightweight subset

**Context.** The AI-friendly layer was requested "as lightweight as possible," because
the project is small and simple for an AI to drive.

**Decision.** Keep only the high-payoff core: a global `--json`, an errors-as-data
envelope, a renderer split (Rich / JSON), and a hand-built `mikrot manifest --json`.
Do **not** add a `schema` command, a synthetic-envelope model registry, or heavy
contract-drift machinery (a single light test that the hand-written shapes match the
Pydantic models is fine). `contract_version` is a plain int. The manifest's enriched
contents (response/error shapes) are specified in DEC-011. A deliberate trade favouring
code simplicity over reference completeness.

## DEC-003. Configuration -- `.env` only, prefix `MIKROT_`

**Context.** Settings must live in a `.env` file, all prefixed `MIKROT_`.

**Decision.** A flat `.env` via `pydantic-settings`
(`SettingsConfigDict(env_prefix="MIKROT_")`). No YAML layer. `.env` files are loaded with
`dotenv.load_dotenv(..., override=False)` (the shell environment wins); the exact set of
files and their order is defined in DEC-010. `MIKROT_PASSWORD` is required; if missing ->
`MikrotError(code="config_missing")`. Pydantic's native `env_file` source is **not**
used (it would break the "no password" test isolation) -- the only `.env` loader is
`load_dotenv`.

## DEC-004. `doctor` -- diagnostics + baseline in one command

**Context.** The tool needs a preflight/diagnostics command that a human or an agent can
run to confirm connectivity before doing real work.

**Decision.** `doctor` runs diagnostic checks (config / reachable / REST) as rows plus
an `overall_status`, then prints baseline router info (identity / resource /
routerboard). One command covers both preflight and smoke-info. `--strict` -> exit 1 on
`warn` / `fail`.

## DEC-005. Keep meaningful exit codes

**Context.** Application errors can be surfaced two ways: always exit `0` (errors-as-data
-- the error is in the body), or keep meaningful per-error exit codes so shell scripts
can branch on the process status.

**Decision.** A hybrid -- emit the structured error envelope (errors-as-data in the
body) **and** keep meaningful exit codes (`router_unreachable` 1, `http_error` 2,
`lease_not_found` 3, `lease_ambiguous` 4, `config_missing` 1). This gives both a
machine-readable error and a meaningful return code for scripts. `doctor` is the
exception: always exit 0, `--strict` -> 1.

> Resolved for the public release: keep the hybrid (meaningful exit codes + errors-as-data).
> The `code -> exit` mapping is also published in the manifest as `exit_codes` (DEC-011) so
> agents can discover it; either way, agents should treat the JSON envelope as the primary
> signal.

## DEC-006. `make-dynamic` via `DELETE`

**Context.** RouterOS REST exposes no `make-dynamic` action, and a PATCH of the
`dynamic` field is rejected (it is a managed field).

**Decision.** "Make dynamic" = `DELETE /ip/dhcp-server/lease/<.id>` (remove the static
entry). A client with an active bound lease keeps its IP until the lease timer expires,
then receives a fresh dynamic lease on its next DHCP renew. The behaviour and its risks
are documented in the command help and the README.

## DEC-007. ASCII-only in `src/` and `tests/`

**Context.** Code and tests should stay portable and lint-clean.

**Decision.** `src/` and `tests/` are ASCII-only English (enforced by ruff `RUF`).
Narrative documentation (`docs/`, `README.md`) is English; non-ASCII typographic
characters are tolerated there but not required.

## DEC-008. Mutations -- dry-run by default

**Decision.** `make-static` / `make-dynamic` default to showing the plan (a `before`
snapshot plus what would be called) and change nothing; `--commit` applies the change
and shows the `after` state.

## DEC-009. One package `src/mikrot`, console-script `mikrot`

**Decision.** `mikrot` is a single package `src/mikrot` (no separate library or
service). hatchling, `[tool.uv] package = true`, console-script
`mikrot = "mikrot.app:main"`. Ruff runs without `TID` (there is no import boundary to
guard).

## DEC-010. Layered `.env` loading (project-local + global) + `MIKROT_CONFIG_HOME`

**Context.** A single project-local `.env` (DEC-003) is inconvenient for a CLI used from
many directories: per-machine defaults (host, user, password) had to be repeated in every
working directory. A user-level config location is the conventional fix.

**Decision.** Load two `.env` files into the environment, both with `override=False`:

1. the project-local `.env` (`find_dotenv(usecwd=True)`), loaded **first**;
2. the global `~/.config/mikrot/.env`, loaded **second**.

Resulting precedence: shell env > project-local `.env` > global `.env` > built-in
defaults. `override=False` everywhere keeps the shell on top; loading the local file
first lets it win over the global one. (`override=True` was rejected: it would let a file
beat real shell/CI variables, breaking ad-hoc overrides and test isolation.)

The global file is **auto-created on first run** as a fully commented scaffold so users
have a discoverable, documented template; an all-commented file contributes nothing until
edited. Creation is best-effort (filesystem errors ignored) and never overwrites an
existing file. The global directory defaults to `~/.config/mikrot` on every OS (a single,
predictable path rather than per-OS dirs) and is overridable via `MIKROT_CONFIG_HOME`
(read from the shell environment, since it decides where the files live) -- this also
makes the loader trivially testable against a tmp directory.

## DEC-011. Manifest carries response/error shapes (`fields` + `error_shape`)

**Context.** Section 5 left open how much of the contract `mikrot manifest` should expose.
Listing only a model name is too thin for an AI consumer; a `schema` command or a model
registry is too heavy for this project.

**Decision.** Enrich the hand-written manifest; no `schema` command.

- Each command's `response_shape` gains `fields: {name -> type}` with a compact type
  vocabulary (`str`/`int`/`float`/`bool`, `str|null`, `object`/`object|null`,
  `array<Model>`, `enum: a|b|c`). A `passthrough: true` flag marks raw RouterOS objects
  (leases) whose field set varies; `fields` then lists only the stable, relied-on keys.
- Nested models referenced as `array<Model>` are documented in a top-level `models` map.
- A top-level `error_shape` documents the fixed errors-as-data envelope
  (`error`/`code`/`fix`/`fix_description`); per-error `context` keys merge on top.
- Per-command `error_codes` list DOMAIN-specific codes only; `infrastructure_errors` apply
  globally and a consumer unions them (`dhcp-leases` -> `[]`, `make-*` ->
  `[lease_not_found, lease_ambiguous]`, `doctor` -> `[]`).
- A top-level `exit_codes` map (`code -> int`) publishes each code's process exit code,
  mirroring the single source `errors._EXIT_CODES` (a light test ties them). `doctor` is
  the exception, documented in its `summary` (always exit 0; `--strict` -> 1). See DEC-005.
- `contract_version` stays a plain int, bumped on ANY contract change: 2 for the response/
  error shapes above, 3 when the `exit_codes` map was added.

Drift guard stays light (not heavy contract machinery): tests assert every manifest code
is registered, per-command codes stay domain-only, and the hand-written `fields` keys
equal the real Pydantic `model_fields`. `Lease` (passthrough) is exempt from the field
check.

## DEC-012. Secret references via password managers (`secretref` + 1Password)

**Context.** Storing `MIKROT_PASSWORD` as plaintext in `.env` is undesirable. We want to
keep the secret in a password manager (1Password first) and reference it from config.

**Decision.** Resolve secret references **in-process** (not by re-exec). A self-contained
package `mikrot/secretref/` resolves values shaped like `op://Vault/Item/field`:

- A **hardcoded prefix -> provider** map (`PREFIX_PROVIDERS`) ties a reference prefix to an
  external CLI and its read command (1Password: prefix `op://`, tool `op`, `op read <ref>`).
  Adding a manager is one map entry.
- Resolution is **value-driven**: only values matching a known prefix are resolved; the
  package needs no knowledge of which variables exist. The host (mikrot) chooses scope by
  passing the `MIKROT_`-prefixed subset of the environment (prefix taken from
  `Settings.model_config["env_prefix"]`).
- The tool's presence is checked (`shutil.which`) **before** any process launch; the secret
  is read via `subprocess` with a timeout. Non-reference values pass through unchanged
  (backward compatible).
- `secretref` stays host-agnostic (no imports from mikrot; its own `SecretResolutionError`).
  The settings layer converts failures to a single errors-as-data code
  `secret_resolution_failed` (infrastructure, exit 1; `contract_version` -> 4).
- Extra providers can be added **without code** via the `SECRETREF_PROVIDERS` env var (a
  JSON array of `{prefix, tool, args}`; an `{ref}` token in `args` is substituted, else the
  reference is appended). Env-defined providers override built-ins on a prefix clash;
  malformed config raises. It is read from the real environment only (it configures the
  resolver, so it is never itself resolved). This is not part of the manifest contract, so
  it does not bump `contract_version`. See `src/mikrot/secretref/README.md`.

**Provider model.** Providers are polymorphic: a base `Provider` with `resolve(value)`, a
`CliProvider` (external tool; what `SECRETREF_PROVIDERS` builds), and an `EnvProvider`
shipped as an **example custom (internal) provider** (prefix `env://`) that resolves
environment variables in-process. `env://${VAR:-default}` hands the expression to the
`expandvars` library rather than re-implementing shell expansion (a small added dependency).
Non-CLI providers are added by subclassing `Provider`.

**Rejected: re-exec under `op run`.** Re-running the process under `op run` via
`os.execvp` is unreliable on Windows (the process is not awaited and the exit code is lost
-- CPython #101191), which would break the meaningful-exit-code contract (DEC-005) on the
primary dev platform; `op run` also strips environment variables (e.g. `COLUMNS`/`TERM`)
that the Rich output relies on. In-process `op read` avoids both.

**Future.** `secretref` is built for later extraction into a standalone distribution.
Caching/batching of `op read` calls is a low-priority backlog idea.
