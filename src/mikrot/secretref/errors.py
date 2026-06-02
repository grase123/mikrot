"""Errors for secretref (no dependency on the host application)."""

from __future__ import annotations


class SecretResolutionError(Exception):
    """A secret reference could not be resolved.

    Carries the offending ``ref`` (the reference string, e.g. ``op://...`` --
    safe to surface, it is not the secret; ``None`` for provider-config errors
    not tied to one reference) and the external ``tool`` involved, so the host
    can build a useful errors-as-data envelope.
    """

    def __init__(
        self, message: str, *, ref: str | None = None, tool: str | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.ref = ref
        self.tool = tool
