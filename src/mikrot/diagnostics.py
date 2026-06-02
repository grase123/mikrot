"""Doctor diagnostics: check-result model + overall-status helper.

A single Pydantic model is the source of truth: deliberately lightweight, with
no separate dataclass mirror kept in sync by a drift test. ``fix`` must be
``None`` or a literal ``"mikrot ..."`` command; multi-step or non-mikrot
remediation goes in ``fix_description``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel

Status = Literal["ok", "warn", "fail"]


class CheckResult(BaseModel):
    """One doctor check outcome."""

    name: str
    status: Status
    detail: str
    fix: str | None = None
    fix_description: str | None = None


class DoctorEnvelope(BaseModel):
    """Top-level ``mikrot doctor`` output.

    ``baseline`` holds router system info (identity/resource/routerboard)
    and is present only when the router was reachable; ``None`` when skipped.
    """

    checks: list[CheckResult]
    overall_status: Status
    baseline: dict[str, Any] | None = None


def compute_overall_status(results: Iterable[CheckResult]) -> Status:
    """Aggregate check statuses with priority ``fail`` > ``warn`` > ``ok``."""
    has_warn = False
    for result in results:
        if result.status == "fail":
            return "fail"
        if result.status == "warn":
            has_warn = True
    return "warn" if has_warn else "ok"
