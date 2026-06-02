"""Tests for dhcp-leases filtering (pure matcher, no network)."""

from __future__ import annotations

from mikrot.commands.dhcp import _lease_matches

_LEASE = {
    "mac-address": "DC:2C:6E:11:22:33",
    "host-name": "printer",
    "status": "bound",
    "comment": "Office printer",
}


def test_no_filters_matches() -> None:
    assert _lease_matches(_LEASE, mac=None, name=None, status=None, comment=None)


def test_mac_name_status_substring_and_exact() -> None:
    assert _lease_matches(_LEASE, mac="6E:11", name=None, status=None, comment=None)
    assert _lease_matches(_LEASE, mac=None, name="PRINT", status=None, comment=None)
    assert _lease_matches(_LEASE, mac=None, name=None, status="bound", comment=None)
    assert not _lease_matches(_LEASE, mac=None, name=None, status="waiting", comment=None)


def test_mac_separator_insensitive() -> None:
    # The lease MAC is colon-separated; all three filter forms must match.
    for needle in ("DC:2C:6E", "DC-2C-6E", "dc2c6e", "2C6E1122"):
        assert _lease_matches(_LEASE, mac=needle, name=None, status=None, comment=None), needle
    assert not _lease_matches(_LEASE, mac="AA:BB", name=None, status=None, comment=None)


def test_comment_substring_case_insensitive() -> None:
    assert _lease_matches(_LEASE, mac=None, name=None, status=None, comment="office")
    assert not _lease_matches(_LEASE, mac=None, name=None, status=None, comment="server")


def test_comment_missing_field_does_not_match() -> None:
    lease = {"mac-address": "x"}
    assert not _lease_matches(lease, mac=None, name=None, status=None, comment="any")


def test_filters_combine_with_and() -> None:
    assert _lease_matches(_LEASE, mac="dc:2c", name="print", status="bound", comment="printer")
    assert not _lease_matches(_LEASE, mac="dc:2c", name="print", status="waiting", comment="printer")
