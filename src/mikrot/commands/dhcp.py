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


def _normalize_mac(value: str) -> str:
    """Strip ``:`` / ``-`` separators and lowercase, so MAC matching is
    separator-insensitive (``DC:2C:6E`` == ``DC-2C-6E`` == ``DC2C6E``)."""
    return value.replace(":", "").replace("-", "").lower()


def _lease_matches(
    lease: dict[str, Any],
    *,
    mac: str | None,
    name: str | None,
    status: str | None,
    comment: str | None,
    address: str | None,
) -> bool:
    """Pure filter for a single lease (substring filters are case-insensitive)."""
    if mac and _normalize_mac(mac) not in _normalize_mac(str(lease.get("mac-address", ""))):
        return False
    if name and name.lower() not in str(lease.get("host-name", "")).lower():
        return False
    if status and status != str(lease.get("status", "")):
        return False
    if comment and comment.lower() not in str(lease.get("comment", "")).lower():
        return False
    if address:
        needle = address.lower()
        in_address = needle in str(lease.get("address", "")).lower()
        in_active = needle in str(lease.get("active-address", "")).lower()
        if not (in_address or in_active):
            return False
    return True


def register(app: typer.Typer) -> None:
    @app.command(
        "dhcp-leases",
        help="List DHCP server leases (/ip/dhcp-server/lease) with optional filters. Aliases: l, d.",
        epilog=(
            "Examples: `mikrot dhcp-leases`, `mikrot l --status bound` (alias), "
            "`mikrot dhcp-leases --mac DC:2C:6E` (filter by vendor OUI), "
            "`mikrot dhcp-leases --comment printer`, "
            "`mikrot dhcp-leases -a 192.168.88` (IP substring), "
            "`mikrot --json dhcp-leases --status bound`."
        ),
    )
    def dhcp_leases(
        ctx: typer.Context,
        mac: str | None = typer.Option(
            None,
            "--mac",
            "-m",
            help="Filter by MAC substring; ':'/'-'/no separator all match (case-insensitive).",
        ),
        name: str | None = typer.Option(
            None,
            "--name",
            "--host",
            "-n",
            help="Filter by host-name substring (case-insensitive).",
        ),
        status: str | None = typer.Option(
            None, "--status", "-s", help="Filter by exact lease status (e.g. bound, waiting)."
        ),
        comment: str | None = typer.Option(
            None, "--comment", "-c", help="Filter by comment substring (case-insensitive)."
        ),
        address: str | None = typer.Option(
            None,
            "--address",
            "--ip",
            "-a",
            "-i",
            help="Filter by IP substring; matches address or active-address.",
        ),
    ) -> None:
        with emit_errors(ctx) as cli_ctx:
            with cli_ctx.client() as client:
                leases: Any = get_json(client, "/ip/dhcp-server/lease")
            if not isinstance(leases, list):
                leases = [leases] if leases else []

            filtered = [
                item
                for item in leases
                if _lease_matches(
                    item, mac=mac, name=name, status=status, comment=comment, address=address
                )
            ]
            filtered.sort(
                key=lambda x: (str(x.get("status", "")), _ip_sort_key(str(x.get("address", ""))))
            )
            cli_ctx.renderer.leases(filtered, total=len(leases))
