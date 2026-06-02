"""`mikrot doctor` -- preflight checks + baseline router info.

Three checks (config password set, router reachable, REST API responds) each
return a :class:`CheckResult` and never raise -- failures are reported in-band
(errors-as-data). When the router is reachable, baseline system info
(identity / resource / routerboard) is appended. ``--strict`` exits 1 unless
``overall_status == "ok"``; otherwise the command always exits 0.
"""

from __future__ import annotations

from typing import Any

import httpx
import typer

from mikrot.context import CliContext
from mikrot.diagnostics import CheckResult, DoctorEnvelope, compute_overall_status
from mikrot.rest import get_one
from mikrot.settings import Settings, load_settings_tolerant

# Short probe so doctor stays snappy when the router is half-up.
_PROBE_TIMEOUT = httpx.Timeout(connect=2.0, read=3.0, write=2.0, pool=2.0)

# Subset of /system/resource and /system/routerboard keys shown in baseline info.
RESOURCE_KEYS = [
    "platform",
    "board-name",
    "architecture-name",
    "version",
    "build-time",
    "factory-software",
    "uptime",
    "cpu",
    "cpu-count",
    "cpu-frequency",
    "cpu-load",
    "total-memory",
    "free-memory",
    "total-hdd-space",
    "free-hdd-space",
    "write-sect-since-reboot",
]
BOARD_KEYS = [
    "model",
    "serial-number",
    "firmware-type",
    "current-firmware",
    "upgrade-firmware",
    "factory-firmware",
    "routerboard",
]


def _check_config_password_set(settings: Settings) -> CheckResult:
    if not settings.password:
        return CheckResult(
            name="config_password_set",
            status="fail",
            detail="MIKROT_PASSWORD is not set",
            fix_description="set MIKROT_PASSWORD in .env (see .env.example)",
        )
    return CheckResult(
        name="config_password_set",
        status="ok",
        detail=f"user={settings.user} host={settings.host}:{settings.port}",
    )


def _check_router_reachable(settings: Settings) -> CheckResult:
    # Any HTTP response (even 401) proves TCP/HTTP reachability; only a
    # transport error counts as a failure here.
    try:
        httpx.get(
            settings.base_url,
            timeout=_PROBE_TIMEOUT,
            auth=(settings.user, settings.password),
        )
    except httpx.RequestError as exc:
        return CheckResult(
            name="router_reachable",
            status="fail",
            detail=f"cannot reach {settings.base_url}: {type(exc).__name__}: {exc}",
            fix_description="check MIKROT_HOST/PORT/SCHEME and network connectivity to the router",
        )
    return CheckResult(
        name="router_reachable", status="ok", detail=f"{settings.base_url} reachable"
    )


def _check_rest_api_responds(settings: Settings) -> CheckResult:
    if not settings.password:
        return CheckResult(
            name="rest_api_responds",
            status="warn",
            detail="skipped: no password (see config_password_set)",
            fix_description="resolve the config_password_set row first",
        )
    try:
        response = httpx.get(
            f"{settings.base_url}/system/identity",
            auth=(settings.user, settings.password),
            timeout=_PROBE_TIMEOUT,
            headers={"Accept": "application/json"},
        )
    except httpx.RequestError as exc:
        return CheckResult(
            name="rest_api_responds",
            status="warn",
            detail=f"skipped: router not reachable ({exc})",
            fix_description="resolve the router_reachable row first",
        )
    if response.status_code != 200:
        return CheckResult(
            name="rest_api_responds",
            status="fail",
            detail=f"GET /system/identity -> HTTP {response.status_code}",
            fix_description=(
                "router answered but the REST API rejected the request; verify the 'www' "
                "service is enabled and MIKROT_USER/MIKROT_PASSWORD are correct"
            ),
        )
    try:
        response.json()
    except ValueError:
        return CheckResult(
            name="rest_api_responds",
            status="fail",
            detail="GET /system/identity returned 200 but the body is not JSON",
            fix_description="verify the endpoint is the RouterOS REST API",
        )
    return CheckResult(
        name="rest_api_responds", status="ok", detail="GET /system/identity -> 200 JSON"
    )


_CHECKS = (
    _check_config_password_set,
    _check_router_reachable,
    _check_rest_api_responds,
)


def run_all_checks(settings: Settings) -> list[CheckResult]:
    return [check(settings) for check in _CHECKS]


def _fetch_baseline(settings: Settings) -> dict[str, Any] | None:
    """Best-effort baseline. Returns ``None`` on any error (reachability is
    already surfaced by the check rows)."""
    try:
        with httpx.Client(
            base_url=settings.base_url,
            auth=(settings.user, settings.password),
            timeout=settings.timeout,
            headers={"Accept": "application/json"},
        ) as client:
            identity = get_one(client, "/system/identity")
            resource = get_one(client, "/system/resource")
            board = get_one(client, "/system/routerboard")
    except Exception:  # baseline is best-effort; reachability is reported by the checks
        return None
    return {
        "identity": identity,
        "resource": {k: resource[k] for k in RESOURCE_KEYS if k in resource},
        "routerboard": {k: board[k] for k in BOARD_KEYS if k in board},
    }


def register(app: typer.Typer) -> None:
    @app.command(
        "doctor",
        help="Run preflight checks against the MikroTik router and show baseline info.",
        epilog=(
            "Example: `mikrot doctor`. `mikrot --json doctor` emits "
            "{checks, overall_status, baseline}. `mikrot doctor --strict` exits 1 on warn or fail."
        ),
    )
    def doctor_cmd(
        ctx: typer.Context,
        strict: bool = typer.Option(
            False,
            "--strict",
            help="Exit 1 unless overall_status == 'ok'. Default: exit 0, errors-as-data.",
        ),
    ) -> None:
        cli_ctx: CliContext = ctx.obj
        settings = load_settings_tolerant()
        results = run_all_checks(settings)
        overall = compute_overall_status(results)
        reachable = next((r for r in results if r.name == "router_reachable"), None)
        baseline = (
            _fetch_baseline(settings) if reachable is not None and reachable.status == "ok" else None
        )
        envelope = DoctorEnvelope(checks=results, overall_status=overall, baseline=baseline)
        cli_ctx.renderer.doctor(envelope.model_dump())
        if strict and overall != "ok":
            raise typer.Exit(code=1)
