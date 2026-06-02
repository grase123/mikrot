"""`mikrot manifest` -- machine-readable self-description for AI consumers.

Lightweight by design: the manifest is a hand-written dict literal. There is
no Typer/click introspection and no synthetic-envelope machinery. The response
shapes (`fields: {name -> type}`) and the error envelope (`error_shape`) are
written by hand here; a light test keeps the model-backed `fields` in sync with
the real Pydantic ``model_fields`` (see ``tests/test_manifest.py``). The
``exit_codes`` map mirrors ``errors._EXIT_CODES`` (single source).

``CONTRACT_VERSION`` is a plain int -- bump it on ANY change to the published
contract (command set, response/error shapes, or code sets) so pinned agents
get a signal.

Type vocabulary used in `fields`:
  ``str`` / ``int`` / ``float`` / ``bool`` -- JSON scalars
  ``str|null`` / ``object|null`` -- nullable scalar / nullable JSON object
  ``object`` -- arbitrary JSON object (dict)
  ``array<Model>`` -- list of the named model (see top-level ``models``)
  ``enum: a|b|c`` -- string restricted to the listed values
"""

from __future__ import annotations

from typing import Any

import typer

from mikrot._version import version_string
from mikrot.context import CliContext
from mikrot.errors import _EXIT_CODES

# Bump on ANY change to the published contract (commands, shapes, code sets).
CONTRACT_VERSION = 4

# Codes that can surface from any command that contacts the router or loads
# settings, via the errors-as-data envelope. Per-command `error_codes` lists
# only DOMAIN-specific codes; a consumer takes the union of a command's
# `error_codes` with these infrastructure codes.
_INFRASTRUCTURE_ERRORS: list[str] = [
    "router_unreachable",       # connect-fail -> exit 1
    "http_error",               # HTTP status  -> exit 2
    "config_missing",           # MIKROT_PASSWORD / .env missing -> exit 1
    "secret_resolution_failed",  # op:// reference could not be resolved -> exit 1
    "unknown",                  # uncategorised path -> exit 1
]

# Shapes for models referenced by name (e.g. `array<CheckResult>`) but not the
# direct response of a command. Model-backed shapes here and in the commands'
# `response_shape.fields` are kept in sync with the Pydantic models by a light
# test (`tests/test_manifest.py`).
_MODELS: dict[str, dict[str, Any]] = {
    "CheckResult": {
        "fields": {
            "name": "str",
            "status": "enum: ok|warn|fail",
            "detail": "str",
            "fix": "str|null",
            "fix_description": "str|null",
        },
    },
}

# Fixed-shape envelope of every errors-as-data failure. `context` (per-error
# extra keys, e.g. `ip`) is merged on top of these fixed keys.
_ERROR_SHAPE: dict[str, Any] = {
    "fields": {
        "error": "str",
        "code": "str",
        "fix": "str|null",
        "fix_description": "str|null",
    },
    "note": (
        "Always present on failure. `code` is one of a command's `error_codes` "
        "or `infrastructure_errors`. Per-error `context` keys (e.g. `ip`: str) "
        "are merged on top of these fixed keys."
    ),
}

# Shared response shape for make-static / make-dynamic.
_LEASE_ACTION_FIELDS: dict[str, str] = {
    "action": "str",
    "ip": "str",
    "lease_id": "str|null",
    "committed": "bool",
    "changed": "bool",
    "note": "str",
    "before": "object|null",
    "after": "object|null",
}

# One entry per leaf command. `response_shape`:
#   kind: "model" (single object) | "list" (array of `model`)
#   model: logical model/envelope name (also a key in `models` when nested)
#   fields: {name -> type} for the model's own keys (see type vocabulary above)
#   passthrough: true marks a raw upstream object whose full field set varies
#     (RouterOS leases); `fields` then lists only the stable, relied-on keys.
# `error_codes`: DOMAIN-specific codes only; infrastructure codes apply on top.
_COMMANDS: list[dict[str, Any]] = [
    {
        "path": ["doctor"],
        "summary": (
            "Diagnostic rows (ok/warn/fail) + overall_status, then baseline router "
            "system info (identity/resource/routerboard). Errors-as-data: exits 0 "
            "unless --strict."
        ),
        "response_shape": {
            "kind": "model",
            "model": "DoctorEnvelope",
            "fields": {
                "checks": "array<CheckResult>",
                "overall_status": "enum: ok|warn|fail",
                "baseline": "object|null",
            },
        },
        "error_codes": [],
    },
    {
        "path": ["dhcp-leases"],
        "summary": (
            "List DHCP leases (full objects in --json). "
            "Filters: --mac / --name / --status / --comment."
        ),
        "response_shape": {
            "kind": "list",
            "model": "Lease",
            "passthrough": True,
            "fields": {
                "address": "str",
                "active-address": "str|null",
                "mac-address": "str",
                "host-name": "str|null",
                "status": "str",
                "dynamic": "str",
                "expires-after": "str|null",
                "last-seen": "str|null",
                "server": "str|null",
                "comment": "str|null",
            },
            "note": (
                "Raw RouterOS lease object; additional fields may be present and "
                "the set varies between bound and waiting leases."
            ),
        },
        "error_codes": [],
    },
    {
        "path": ["make-static"],
        "summary": "Convert a dynamic lease to static (dry-run by default; --commit applies).",
        "response_shape": {
            "kind": "model",
            "model": "LeaseActionEnvelope",
            "fields": dict(_LEASE_ACTION_FIELDS),
        },
        "error_codes": ["lease_not_found", "lease_ambiguous"],
    },
    {
        "path": ["make-dynamic"],
        "summary": "Convert a static lease back to dynamic via DELETE (dry-run; --commit applies).",
        "response_shape": {
            "kind": "model",
            "model": "LeaseActionEnvelope",
            "fields": dict(_LEASE_ACTION_FIELDS),
        },
        "error_codes": ["lease_not_found", "lease_ambiguous"],
    },
]


def build_manifest() -> dict[str, Any]:
    """Assemble the manifest by hand (no introspection)."""
    return {
        "version": version_string(),
        "contract_version": CONTRACT_VERSION,
        "commands": [dict(command) for command in _COMMANDS],
        "models": {name: dict(shape) for name, shape in _MODELS.items()},
        "error_shape": dict(_ERROR_SHAPE),
        "infrastructure_errors": list(_INFRASTRUCTURE_ERRORS),
        # code -> process exit code (single source: errors._EXIT_CODES).
        # `doctor` is the documented exception (always exit 0; --strict -> 1).
        "exit_codes": dict(_EXIT_CODES),
    }


def register(app: typer.Typer) -> None:
    @app.command(
        "manifest",
        help="Print a machine-readable spec of the CLI (version, commands, shapes, error codes).",
        epilog="Use with the global --json flag: `mikrot --json manifest`. --compact minifies JSON.",
    )
    def manifest_cmd(
        ctx: typer.Context,
        compact: bool = typer.Option(
            False, "--compact", help="Minified JSON (no indentation). Only affects --json output."
        ),
    ) -> None:
        cli_ctx: CliContext = ctx.obj
        cli_ctx.renderer.data(build_manifest(), compact=compact)
