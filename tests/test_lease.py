"""Tests for the pure lease-selection logic used by make-static/make-dynamic.

The fetch + mutation paths talk to the router and are exercised live (read
side) / manually (commit side); the selection logic is unit-tested here.
"""

from __future__ import annotations

import pytest

from mikrot.commands.lease import _select_lease
from mikrot.errors import MikrotError

_LEASES = [
    {".id": "*1", "address": "1.1.1.1"},
    {".id": "*2", "address": "2.2.2.2"},
    {".id": "*3", "address": "2.2.2.2"},
]


def test_select_unique() -> None:
    assert _select_lease(_LEASES, "1.1.1.1")[".id"] == "*1"


def test_select_not_found() -> None:
    with pytest.raises(MikrotError) as excinfo:
        _select_lease(_LEASES, "9.9.9.9")
    err = excinfo.value
    assert err.code == "lease_not_found"
    assert err.exit_code == 3
    assert err.context["ip"] == "9.9.9.9"


def test_select_ambiguous() -> None:
    with pytest.raises(MikrotError) as excinfo:
        _select_lease(_LEASES, "2.2.2.2")
    err = excinfo.value
    assert err.code == "lease_ambiguous"
    assert err.exit_code == 4
    assert err.context["count"] == 2
