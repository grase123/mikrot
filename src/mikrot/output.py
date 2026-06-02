"""CLI output: Rich (human) and JSON (machine) renderers.

Commands never print directly -- they call ``ctx.obj.renderer.X(...)``. The
global ``--json`` flag selects :class:`JsonRenderer` (exactly one JSON
document per call) over :class:`RichRenderer` (tables + colour). Keeping the
output split behind one interface is what makes ``--json`` work uniformly
across every command.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.table import Table

from mikrot.errors import MikrotError

# Column subset shown by the Rich `dhcp-leases` table. JSON emits the full
# lease objects (~19 fields) instead.
_LEASE_COLUMNS = [
    "address",
    "active-address",
    "mac-address",
    "host-name",
    "status",
    "dynamic",
    "expires-after",
    "last-seen",
    "server",
    "comment",
]

# Table frames rendered at 30% grey so borders recede behind the content.
_BORDER_STYLE = "grey30"

_STATUS_COLOUR = {"ok": "green", "warn": "yellow", "fail": "red"}
_VERDICT = {
    "ok": "[green]all checks passed[/green]",
    "warn": "[yellow]checks passed with warnings[/yellow]",
    "fail": "[red]one or more checks failed[/red]",
}


class Renderer(ABC):
    """Output strategy. Implementations: :class:`RichRenderer`, :class:`JsonRenderer`."""

    @abstractmethod
    def error(self, err: MikrotError) -> None:
        """Render an error: Rich -> red line; JSON -> envelope dict."""

    @abstractmethod
    def doctor(self, payload: dict[str, Any]) -> None:
        """Render a doctor envelope (check rows + verdict + baseline)."""

    @abstractmethod
    def leases(self, leases: Sequence[dict[str, Any]], *, total: int) -> None:
        """Render DHCP leases. Rich shows a column subset; JSON the full list."""

    @abstractmethod
    def lease_action(self, envelope: dict[str, Any]) -> None:
        """Render a make-static / make-dynamic result envelope."""

    @abstractmethod
    def data(self, obj: Any, *, compact: bool = False) -> None:
        """Emit a raw JSON-able payload (used by ``manifest``)."""


class RichRenderer(Renderer):
    """Human-facing renderer: Rich tables, panels and colour."""

    def __init__(self, console: Console | None = None) -> None:
        # Windows: stdout/stderr default to the OEM codepage -> Cyrillic
        # renders as garbage. Reconfigure to UTF-8 BEFORE Console init (Rich
        # captures sys.stdout.encoding at construction). Guard: not every stream
        # has .reconfigure (e.g. test-capture streams), and some raise.
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (ValueError, OSError):
                    pass
        self._console = console or Console()

    def _kv_panel(
        self, title: str, data: dict[str, Any], *, keys: Sequence[str] | None = None
    ) -> None:
        table = Table(
            show_header=False,
            box=None,
            title=title,
            title_style="bold cyan",
            title_justify="left",
        )
        table.add_column("key", style="cyan", no_wrap=True)
        table.add_column("value", style="white")
        items = (
            list(data.items())
            if keys is None
            else [(k, data[k]) for k in keys if k in data]
        )
        if not items:
            table.add_row("(empty)", "")
        for key, value in items:
            table.add_row(str(key), str(value))
        self._console.print(table)
        self._console.print()

    def error(self, err: MikrotError) -> None:
        # Escape "[error]" so Rich does not parse it as a style tag.
        self._console.print(rf"[red]\[error][/red] {err}")
        if err.fix:
            self._console.print(f"  [dim]fix:[/dim] {err.fix}")
        if err.fix_description:
            self._console.print(f"  [dim]hint:[/dim] {err.fix_description}")
        for key, value in err.context.items():
            self._console.print(f"  [dim]{key}:[/dim] {value}")
        self._console.print()

    def doctor(self, payload: dict[str, Any]) -> None:
        table = Table(title="mikrot doctor", title_justify="left", border_style=_BORDER_STYLE)
        table.add_column("check")
        table.add_column("status")
        table.add_column("detail")
        for row in payload.get("checks", []):
            colour = _STATUS_COLOUR.get(row["status"], "")
            status_cell = f"[{colour}]{row['status']}[/{colour}]" if colour else row["status"]
            detail = row["detail"]
            if row.get("fix"):
                detail = f"{detail}\n  [dim]fix:[/dim] {row['fix']}"
            if row.get("fix_description"):
                detail = f"{detail}\n  [dim]hint:[/dim] {row['fix_description']}"
            table.add_row(row["name"], status_cell, detail)
        self._console.print(table)
        overall = payload.get("overall_status", "fail")
        self._console.print(_VERDICT.get(overall, f"[red]unknown overall_status: {overall}[/red]"))
        self._console.print()
        baseline = payload.get("baseline")
        if baseline:
            self._kv_panel("system/identity", baseline.get("identity", {}))
            self._kv_panel("system/resource", baseline.get("resource", {}))
            self._kv_panel("system/routerboard", baseline.get("routerboard", {}))

    def leases(self, leases: Sequence[dict[str, Any]], *, total: int) -> None:
        if not leases:
            self._console.print(
                f"[grey30]no leases match filters (total in DHCP table: {total})[/grey30]"
            )
            self._console.print()
            return
        table = Table(
            title=f"dhcp-server/lease  (total={total}, shown={len(leases)})",
            title_justify="left",
            border_style=_BORDER_STYLE,
        )
        for column in _LEASE_COLUMNS:
            table.add_column(column)
        for lease in leases:
            # Dim offline (waiting) rows so live (bound) leases stand out.
            style = "grey30" if str(lease.get("status", "")) == "waiting" else None
            table.add_row(*(str(lease.get(column, "")) for column in _LEASE_COLUMNS), style=style)
        self._console.print()
        self._console.print(table)
        self._console.print()

    def lease_action(self, envelope: dict[str, Any]) -> None:
        action = envelope.get("action", "lease-action")
        ip = envelope.get("ip", "")
        self._console.print(f"[bold]{action}[/bold] {ip}", highlight=False)
        if envelope.get("note"):
            self._console.print(f"  {envelope['note']}", highlight=False)
        if envelope.get("before"):
            self._kv_panel("before", envelope["before"], keys=_LEASE_COLUMNS)
        if envelope.get("after"):
            self._kv_panel("after", envelope["after"], keys=_LEASE_COLUMNS)

    def data(self, obj: Any, *, compact: bool = False) -> None:
        # `compact` only affects machine output; Rich always pretty-prints.
        del compact
        self._console.print_json(json.dumps(obj, ensure_ascii=False, default=str))
        self._console.print()


class JsonRenderer(Renderer):
    """Machine-facing renderer: one JSON document per call. Bypasses Rich.

    ``ensure_ascii=False`` so Cyrillic DHCP host-names/comments survive the
    round-trip; ``default=str`` so unexpected types never blow up.
    """

    @staticmethod
    def _emit(payload: Any, *, compact: bool = False) -> None:
        print(json.dumps(payload, ensure_ascii=False, indent=None if compact else 2, default=str))

    def error(self, err: MikrotError) -> None:
        self._emit(err.as_envelope())

    def doctor(self, payload: dict[str, Any]) -> None:
        self._emit(payload)

    def leases(self, leases: Sequence[dict[str, Any]], *, total: int) -> None:
        # `total` is a Rich-only label; JSON consumers get the full lease list.
        del total
        self._emit(list(leases))

    def lease_action(self, envelope: dict[str, Any]) -> None:
        self._emit(envelope)

    def data(self, obj: Any, *, compact: bool = False) -> None:
        self._emit(obj, compact=compact)
