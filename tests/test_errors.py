"""Tests for the MikrotError envelope: fix-prefix rule, exit codes, shape."""

from __future__ import annotations

import pytest

from mikrot.errors import ERROR_CODES, MikrotError


def test_fix_must_use_mikrot_prefix() -> None:
    # A runnable fix must start with "mikrot "; anything else is rejected.
    with pytest.raises(ValueError):
        MikrotError("boom", code="router_unreachable", fix="restart the router")
    # The mikrot prefix and None are both accepted.
    assert MikrotError("boom", fix="mikrot doctor").fix == "mikrot doctor"
    assert MikrotError("boom", fix=None).fix is None


@pytest.mark.parametrize(
    ("code", "expected_exit"),
    [
        ("router_unreachable", 1),
        ("http_error", 2),
        ("lease_not_found", 3),
        ("lease_ambiguous", 4),
        ("config_missing", 1),
        ("unknown", 1),
        ("something_unmapped", 1),  # default
    ],
)
def test_exit_code_mapping(code: str, expected_exit: int) -> None:
    assert MikrotError("m", code=code).exit_code == expected_exit


def test_known_codes_are_registered() -> None:
    # Every mapped code (except the synthetic default test value) is published.
    for code in ("router_unreachable", "http_error", "lease_not_found",
                 "lease_ambiguous", "config_missing", "unknown"):
        assert code in ERROR_CODES


def test_envelope_shape_and_context_merge() -> None:
    err = MikrotError(
        "no DHCP lease found for address 1.2.3.4",
        code="lease_not_found",
        context={"ip": "1.2.3.4"},
    )
    env = err.as_envelope()
    # Fixed keys always present (fix / fix_description may be None).
    assert set(env) >= {"error", "code", "fix", "fix_description"}
    assert env["code"] == "lease_not_found"
    assert env["fix"] is None
    assert env["fix_description"] is None
    # Context is merged on top.
    assert env["ip"] == "1.2.3.4"
