"""Tests for dhcp-leases filtering (pure matcher, no network)."""

from __future__ import annotations

from typing import Any

from mikrot.commands.dhcp import _lease_matches

_LEASE = {
    "address": "192.168.88.50",
    "active-address": "192.168.88.50",
    "mac-address": "DC:2C:6E:11:22:33",
    "host-name": "printer",
    "status": "bound",
    "comment": "Office printer",
}


def _m(
    lease: dict[str, Any] | None = None,
    *,
    mac: str | None = None,
    name: str | None = None,
    status: str | None = None,
    comment: str | None = None,
    address: str | None = None,
) -> bool:
    target = _LEASE if lease is None else lease
    return _lease_matches(
        target, mac=mac, name=name, status=status, comment=comment, address=address
    )


def test_no_filters_matches() -> None:
    assert _m()


def test_mac_name_status_substring_and_exact() -> None:
    assert _m(mac="6E:11")
    assert _m(name="PRINT")
    assert _m(status="bound")
    assert not _m(status="waiting")


def test_mac_separator_insensitive() -> None:
    # The lease MAC is colon-separated; all three filter forms must match.
    for needle in ("DC:2C:6E", "DC-2C-6E", "dc2c6e", "2C6E1122"):
        assert _m(mac=needle), needle
    assert not _m(mac="AA:BB")


def test_comment_substring_case_insensitive() -> None:
    assert _m(comment="office")
    assert not _m(comment="server")


def test_comment_missing_field_does_not_match() -> None:
    assert not _m({"mac-address": "x"}, comment="any")


def test_address_matches_address_field() -> None:
    assert _m(address="192.168.88.50")
    assert _m(address="88.50")  # substring
    assert not _m(address="10.0.0")


def test_address_matches_either_field() -> None:
    lease = {"address": "0.0.0.0", "active-address": "192.168.88.77", "status": "bound"}
    assert _m(lease, address="88.77")     # matches active-address
    assert _m(lease, address="0.0.0.0")   # matches address
    assert not _m(lease, address="10.0.0.1")


def test_address_active_field_missing_ok() -> None:
    # `waiting` leases have no active-address key; address-only match still works.
    lease = {"address": "192.168.88.5", "status": "waiting"}
    assert _m(lease, address="88.5")
    assert not _m(lease, address="99.9")


def test_filters_combine_with_and() -> None:
    assert _m(mac="dc:2c", name="print", status="bound", comment="printer", address="88.50")
    assert not _m(mac="dc:2c", name="print", status="waiting", comment="printer")
