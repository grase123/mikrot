"""`mikrot make-static` / `mikrot make-dynamic` -- DHCP lease mutations.

Both look a lease up by exact IP and default to a dry-run (show the planned
action, change nothing); ``--commit`` applies it.

REST asymmetry (see docs): ``make-static`` is a real action endpoint, but
RouterOS exposes no ``make-dynamic`` action and rejects a PATCH of the
``dynamic`` field -- so "make dynamic" is implemented as a ``DELETE`` of the
static reservation. A bound client keeps its IP until the lease timer expires,
then re-DHCPs into a fresh dynamic entry.
"""

from __future__ import annotations

from typing import Any

import typer

from mikrot.context import emit_errors
from mikrot.errors import MikrotError
from mikrot.models import LeaseActionEnvelope
from mikrot.rest import get_json, request


def _select_lease(leases: list[dict[str, Any]], ip: str) -> dict[str, Any]:
    """Return the single lease whose ``address`` equals ``ip``.

    Raises ``lease_not_found`` (exit 3) or ``lease_ambiguous`` (exit 4).
    """
    matches = [lease for lease in leases if str(lease.get("address", "")) == ip]
    if not matches:
        raise MikrotError(
            f"no DHCP lease found for address {ip}",
            code="lease_not_found",
            context={"ip": ip},
        )
    if len(matches) > 1:
        raise MikrotError(
            f"{len(matches)} leases match address {ip} -- ambiguous",
            code="lease_ambiguous",
            context={"ip": ip, "count": len(matches)},
        )
    return matches[0]


def _fetch_lease(client: Any, ip: str) -> dict[str, Any]:
    leases = get_json(client, "/ip/dhcp-server/lease")
    if not isinstance(leases, list):
        leases = [leases] if leases else []
    return _select_lease(leases, ip)


def _find_after(client: Any, ip: str) -> dict[str, Any] | None:
    leases = get_json(client, "/ip/dhcp-server/lease")
    if not isinstance(leases, list):
        leases = [leases] if leases else []
    matches = [lease for lease in leases if str(lease.get("address", "")) == ip]
    return matches[0] if matches else None


def register(app: typer.Typer) -> None:
    @app.command(
        "make-static",
        help="Convert a dynamic DHCP lease into a static reservation (lookup by IP).",
        epilog=(
            "Default is dry-run (no change). Example: `mikrot make-static 192.168.88.50 --commit`. "
            "Requires the router user to hold the 'policy' permission flag."
        ),
    )
    def make_static(
        ctx: typer.Context,
        ip: str = typer.Argument(..., help="IP address of the lease to convert to static."),
        commit: bool = typer.Option(
            False, "--commit", help="Apply the change (default: dry-run only)."
        ),
    ) -> None:
        with emit_errors(ctx) as cli_ctx:
            with cli_ctx.client() as client:
                lease = _fetch_lease(client, ip)
                lease_id = str(lease.get(".id", "")) or None
                if str(lease.get("dynamic", "")).lower() == "false":
                    envelope = LeaseActionEnvelope(
                        action="make-static",
                        ip=ip,
                        lease_id=lease_id,
                        note="lease is already static (dynamic=false) -- no-op",
                        before=lease,
                    )
                elif not commit:
                    envelope = LeaseActionEnvelope(
                        action="make-static",
                        ip=ip,
                        lease_id=lease_id,
                        note=(
                            f"dry-run: would POST /ip/dhcp-server/lease/make-static numbers={lease_id}. "
                            "Pass --commit to apply."
                        ),
                        before=lease,
                    )
                else:
                    request(
                        client,
                        "POST",
                        "/ip/dhcp-server/lease/make-static",
                        json={"numbers": lease_id},
                    )
                    envelope = LeaseActionEnvelope(
                        action="make-static",
                        ip=ip,
                        lease_id=lease_id,
                        committed=True,
                        changed=True,
                        note="converted to static reservation",
                        before=lease,
                        after=_find_after(client, ip),
                    )
            cli_ctx.renderer.lease_action(envelope.model_dump())

    @app.command(
        "make-dynamic",
        help="Convert a static DHCP reservation back into a dynamic lease (lookup by IP).",
        epilog=(
            "Default is dry-run. Implemented as DELETE of the static entry (RouterOS REST has no "
            "make-dynamic action). Example: `mikrot make-dynamic 192.168.88.50 --commit`."
        ),
    )
    def make_dynamic(
        ctx: typer.Context,
        ip: str = typer.Argument(..., help="IP address of the lease to convert to dynamic."),
        commit: bool = typer.Option(
            False, "--commit", help="Apply the change (default: dry-run only)."
        ),
    ) -> None:
        with emit_errors(ctx) as cli_ctx:
            with cli_ctx.client() as client:
                lease = _fetch_lease(client, ip)
                lease_id = str(lease.get(".id", "")) or None
                if str(lease.get("dynamic", "")).lower() == "true":
                    envelope = LeaseActionEnvelope(
                        action="make-dynamic",
                        ip=ip,
                        lease_id=lease_id,
                        note="lease is already dynamic (dynamic=true) -- no-op",
                        before=lease,
                    )
                elif not commit:
                    envelope = LeaseActionEnvelope(
                        action="make-dynamic",
                        ip=ip,
                        lease_id=lease_id,
                        note=(
                            f"dry-run: would DELETE /ip/dhcp-server/lease/{lease_id} "
                            "(removes static entry; client re-DHCPs on next renew). Pass --commit to apply."
                        ),
                        before=lease,
                    )
                else:
                    request(client, "DELETE", f"/ip/dhcp-server/lease/{lease_id}")
                    envelope = LeaseActionEnvelope(
                        action="make-dynamic",
                        ip=ip,
                        lease_id=lease_id,
                        committed=True,
                        changed=True,
                        note=(
                            "static reservation removed; client will get a fresh dynamic lease "
                            "on its next DHCP renew"
                        ),
                        before=lease,
                        after=_find_after(client, ip),
                    )
            cli_ctx.renderer.lease_action(envelope.model_dump())
