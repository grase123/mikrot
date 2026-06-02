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
    mac: list[str],
    name: list[str],
    status: list[str],
    comment: list[str],
    address: list[str],
) -> bool:
    """Pure filter for a single lease.

    Each option is a list of values: a lease matches an option if it matches ANY
    of its values (OR); options are combined with AND; an empty list means the
    option is not applied. Substring matches are case-insensitive.
    """
    if mac:
        lease_mac = _normalize_mac(str(lease.get("mac-address", "")))
        if not any(_normalize_mac(value) in lease_mac for value in mac):
            return False
    if name:
        host = str(lease.get("host-name", "")).lower()
        if not any(value.lower() in host for value in name):
            return False
    if status and str(lease.get("status", "")) not in status:
        return False
    if comment:
        text = str(lease.get("comment", "")).lower()
        if not any(value.lower() in text for value in comment):
            return False
    if address:
        addr = str(lease.get("address", "")).lower()
        active = str(lease.get("active-address", "")).lower()
        if not any(value.lower() in addr or value.lower() in active for value in address):
            return False
    return True


def register(app: typer.Typer) -> None:
    @app.command(
        "dhcp-leases",
        help="List DHCP server leases (/ip/dhcp-server/lease) with optional filters. Aliases: l, d.",
        epilog=(
            "Filters are repeatable: OR within an option, AND across options. "
            "Examples: `mikrot l`, `mikrot l -a 10.0.0.5 -a 10.0.0.7` (any of several IPs), "
            "`mikrot dhcp-leases -s bound -s waiting`, "
            "`mikrot dhcp-leases --mac DC:2C:6E` (vendor OUI), "
            "`mikrot --json dhcp-leases --comment printer`."
        ),
    )
    def dhcp_leases(
        ctx: typer.Context,
        mac: list[str] = typer.Option(
            [],
            "--mac",
            "-m",
            help="Filter by MAC substring; repeatable (OR). ':'/'-'/no separator all match.",
        ),
        name: list[str] = typer.Option(
            [],
            "--name",
            "--host",
            "-n",
            help="Filter by host-name substring; repeatable (OR).",
        ),
        status: list[str] = typer.Option(
            [], "--status", "-s", help="Filter by exact lease status; repeatable (OR)."
        ),
        comment: list[str] = typer.Option(
            [], "--comment", "-c", help="Filter by comment substring; repeatable (OR)."
        ),
        address: list[str] = typer.Option(
            [],
            "--address",
            "--ip",
            "-a",
            "-i",
            help="Filter by IP substring; repeatable (OR). Matches address or active-address.",
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
