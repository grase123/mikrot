"""Tests for doctor: status aggregation, checks, and CLI exit semantics.

httpx is patched so no real router is contacted. ``.env`` loading is neutralized
suite-wide by ``conftest.py``; ``MIKROT_PASSWORD`` is set explicitly so the
config check passes and the failure comes purely from the (simulated)
unreachable router.
"""

from __future__ import annotations

import json

import httpx
import pytest

from mikrot.commands import doctor as doctor_mod
from mikrot.diagnostics import CheckResult, compute_overall_status
from mikrot.settings import Settings, load_settings_tolerant


def test_overall_status_priority() -> None:
    ok = CheckResult(name="a", status="ok", detail="")
    warn = CheckResult(name="b", status="warn", detail="")
    fail = CheckResult(name="c", status="fail", detail="")
    assert compute_overall_status([ok, ok]) == "ok"
    assert compute_overall_status([ok, warn]) == "warn"
    assert compute_overall_status([ok, warn, fail]) == "fail"


def test_config_password_check() -> None:
    assert doctor_mod._check_config_password_set(Settings(password="")).status == "fail"
    assert doctor_mod._check_config_password_set(Settings(password="x")).status == "ok"


@pytest.fixture
def router_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROT_PASSWORD", "secret")

    def _raise(*args: object, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(doctor_mod.httpx, "get", _raise)


def test_run_all_checks_router_down(router_down: None) -> None:
    results = doctor_mod.run_all_checks(load_settings_tolerant())
    by_name = {r.name: r for r in results}
    assert by_name["config_password_set"].status == "ok"
    assert by_name["router_reachable"].status == "fail"
    assert by_name["rest_api_responds"].status == "warn"
    assert compute_overall_status(results) == "fail"


def _invoke(*argv: str) -> tuple[int, str]:
    from typer.testing import CliRunner

    from mikrot.app import app as cli_app

    result = CliRunner().invoke(cli_app, list(argv))
    return result.exit_code, result.stdout


def test_doctor_default_exits_zero(router_down: None) -> None:
    # Errors-as-data: a failing router does NOT make doctor exit non-zero.
    code, out = _invoke("--json", "doctor")
    assert code == 0
    data = json.loads(out)
    assert data["overall_status"] == "fail"
    assert data["baseline"] is None


def test_doctor_strict_exits_one(router_down: None) -> None:
    code, _ = _invoke("doctor", "--strict")
    assert code == 1
