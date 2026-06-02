"""CLI context object + error-mapping helper.

The root Typer callback stores a :class:`CliContext` on ``ctx.obj``; every
command reads its renderer (and, for router-touching commands, a lazily
built httpx client) from there. :func:`emit_errors` is the single place that
turns a :class:`MikrotError` into a rendered envelope plus the matching
process exit code.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import httpx
import typer

from mikrot.errors import MikrotError
from mikrot.output import Renderer
from mikrot.rest import make_client
from mikrot.settings import Settings, load_settings


@dataclass
class CliContext:
    """Per-invocation state shared between the root callback and commands."""

    renderer: Renderer
    _settings: Settings | None = None

    def settings(self) -> Settings:
        """Lazily load settings (raises ``config_missing`` if no password)."""
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    def client(self) -> httpx.Client:
        """Build a configured httpx client; caller closes it via ``with``."""
        return make_client(self.settings())


@contextmanager
def emit_errors(ctx: typer.Context) -> Iterator[CliContext]:
    """Render any :class:`MikrotError` and exit with its code.

    Wrap a command body in ``with emit_errors(ctx) as cli_ctx:``. The original
    tool's exit codes (1 connect, 2 HTTP, 3 not-found, 4 ambiguous) are
    preserved while the error itself is still emitted as structured data.
    """
    cli_ctx: CliContext = ctx.obj
    try:
        yield cli_ctx
    except MikrotError as err:
        cli_ctx.renderer.error(err)
        raise typer.Exit(code=err.exit_code) from err
