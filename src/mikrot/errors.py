"""Structured errors for mikrot (errors-as-data).

A :class:`MikrotError` carries a stable snake_case ``code``, an optional
runnable ``fix`` command (must start with ``"mikrot "`` or be ``None``),
free-form ``fix_description`` prose, and an extra ``context`` dict that is
merged into the JSON envelope. Each code maps to a process exit code
preserved verbatim from the original standalone tool: connect-fail 1,
HTTP-status 2, not-found 3, ambiguous 4.
"""

from __future__ import annotations

from typing import Any

# Stable codes published by `mikrot manifest`. Tiers (comment-only, no
# separate registry): infrastructure -> router_unreachable / http_error /
# config_missing / secret_resolution_failed / unknown; command-level ->
# lease_not_found / lease_ambiguous.
ERROR_CODES: frozenset[str] = frozenset(
    {
        "router_unreachable",
        "http_error",
        "lease_not_found",
        "lease_ambiguous",
        "config_missing",
        "secret_resolution_failed",
        "unknown",
    }
)

# Per-code process exit code. Load-bearing: matches the original tool
# exactly. Do not renumber.
_EXIT_CODES: dict[str, int] = {
    "router_unreachable": 1,
    "http_error": 2,
    "lease_not_found": 3,
    "lease_ambiguous": 4,
    "config_missing": 1,
    "secret_resolution_failed": 1,
    "unknown": 1,
}

# `fix`, when set, MUST be an executable mikrot command (or None).
_FIX_PREFIX = "mikrot "


class MikrotError(Exception):
    """A domain error rendered as a stable JSON/Rich envelope.

    The structured payload is the contract; ``fix`` is a literal command an
    agent can run verbatim, while multi-step or non-mikrot remediation goes
    in ``fix_description``.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "unknown",
        fix: str | None = None,
        fix_description: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if fix is not None and not fix.startswith(_FIX_PREFIX):
            raise ValueError(
                "MikrotError.fix must start with the mikrot prefix or be None; "
                "for free-form guidance use fix_description instead."
            )
        self.message = message
        self.code = code
        self.fix = fix
        self.fix_description = fix_description
        self.context: dict[str, Any] = dict(context or {})
        self.exit_code: int = _EXIT_CODES.get(code, 1)

    def as_envelope(self) -> dict[str, Any]:
        """Fixed-shape envelope: error/code/fix/fix_description + context.

        ``fix`` and ``fix_description`` are always present (may be ``null``)
        so a consumer reads ``payload["fix"]`` without a key-presence check.
        """
        envelope: dict[str, Any] = {
            "error": self.message,
            "code": self.code,
            "fix": self.fix,
            "fix_description": self.fix_description,
        }
        envelope.update(self.context)
        return envelope
