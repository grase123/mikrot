"""`mikrot dhcp-leases` -- list DHCP server leases.

Reads ``/ip/dhcp-server/lease``, applies optional substring/status filters,
sorts by status then IP, and renders via the active renderer. Rich shows a
column subset with ``waiting`` rows dimmed; ``--json`` emits the full lease
objects (~19 fields).
"""

from __future__ import annotations

import ipaddress
from typing import Any

import typer

from mikrot.context import emit_errors
from mikrot.rest import get_json


def _ip_sort_key(addr: str) -> tuple[int, ...]:
    try:
        return tuple(ipaddress.ip_address(addr).packed)
    except (ValueError, TypeError):
        return (0,)


def register(app: typer.Typer) -> None:
    @app.command(
        "dhcp-leases",
        help="List DHCP server leases (/ip/dhcp-server/lease) with optional filters.",
        epilog=(
            "Examples: `mikrot dhcp-leases`, `mikrot dhcp-leases --mac DC:2C:6E` "
            "(filter by vendor OUI), `mikrot --json dhcp-leases --status bound`."
        ),
    )
    def dhcp_leases(
        ctx: typer.Context,
        mac: str | None = typer.Option(
            None, "--mac", help="Filter by MAC substring (case-insensitive)."
        ),
        name: str | None = typer.Option(
            None, "--name", help="Filter by host-name substring (case-insensitive)."
        ),
        status: str | None = typer.Option(
            None, "--status", help="Filter by exact lease status (e.g. bound, waiting)."
        ),
    ) -> None:
        with emit_errors(ctx) as cli_ctx:
            with cli_ctx.client() as client:
                leases: Any = get_json(client, "/ip/dhcp-server/lease")
            if not isinstance(leases, list):
                leases = [leases] if leases else []

            def _match(lease: dict[str, Any]) -> bool:
                if mac and mac.lower() not in str(lease.get("mac-address", "")).lower():
                    return False
                if name and name.lower() not in str(lease.get("host-name", "")).lower():
                    return False
                if status and status != str(lease.get("status", "")):
                    return False
                return True

            filtered = [item for item in leases if _match(item)]
            filtered.sort(
                key=lambda x: (str(x.get("status", "")), _ip_sort_key(str(x.get("address", ""))))
            )
            cli_ctx.renderer.leases(filtered, total=len(leases))
