"""Response models for mikrot (documented in ``mikrot manifest``).

Lightweight by design: only the lease-action result needs a typed shape.
DHCP leases are passed through as raw dicts (their field set varies between
``bound`` and ``waiting``), and doctor models live in
:mod:`mikrot.diagnostics`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LeaseActionEnvelope(BaseModel):
    """Result of ``make-static`` / ``make-dynamic`` (dry-run or committed).

    ``changed`` is ``False`` for dry-runs and for already-in-target-state
    no-ops; ``after`` is populated only after a committed change.
    """

    action: str
    ip: str
    lease_id: str | None = None
    committed: bool = False
    changed: bool = False
    note: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
