"""Top-level Typer application for the ``mikrot`` CLI.

Each command lives in its own module under ``mikrot/commands/`` and exposes a
``register(app)`` function. The global ``--json`` flag is hoisted to the front
of argv in :func:`main` so it may appear before or after the subcommand.
"""

from __future__ import annotations

import sys

import typer

from mikrot._version import version_string
from mikrot.commands import dhcp as dhcp_cmd
from mikrot.commands import doctor as doctor_cmd
from mikrot.commands import lease as lease_cmd
from mikrot.commands import manifest as manifest_cmd
from mikrot.context import CliContext
from mikrot.output import JsonRenderer, RichRenderer

# Global flags accepted by the root callback. `_hoist_global_flags` moves them
# to the front so `mikrot dhcp-leases --json` works (Click only parses an
# option at the level where it is declared).
_GLOBAL_BOOL_FLAGS = frozenset({"--json", "--version", "-V"})


def _hoist_global_flags(argv: list[str]) -> list[str]:
    """Move global flags to the front so Click sees them at the root level."""
    pre: list[str] = []
    rest: list[str] = []
    for arg in argv:
        name = arg.split("=", 1)[0] if arg.startswith("--") and "=" in arg else arg
        if name in _GLOBAL_BOOL_FLAGS:
            pre.append(arg)
        else:
            rest.append(arg)
    return pre + rest


_ROOT_EPILOG = (
    "Use `mikrot <command> --help` for command-specific help and examples. "
    "The global `--json` flag may appear before or after the subcommand. "
    "Full machine-readable spec: `mikrot manifest --json`."
)

app = typer.Typer(
    name="mikrot",
    help="MikroTik RouterOS REST helper CLI.",
    epilog=_ROOT_EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)

doctor_cmd.register(app)
dhcp_cmd.register(app)
lease_cmd.register(app)
manifest_cmd.register(app)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit one JSON document per call instead of Rich tables/text. AI- and script-friendly.",
    ),
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version and exit.", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(f"mikrot {version_string()}")
        raise typer.Exit()
    renderer = JsonRenderer() if json_output else RichRenderer()
    ctx.obj = CliContext(renderer=renderer)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    """Console-script entry point declared in pyproject.toml."""
    sys.argv[1:] = _hoist_global_flags(sys.argv[1:])
    app()


if __name__ == "__main__":
    main()
