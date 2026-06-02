"""Smoke tests: package imports, CLI registers, --version and manifest emit
valid output in both Rich and JSON modes."""

from __future__ import annotations

import json

from typer.testing import CliRunner


def _invoke(*argv: str) -> tuple[int, str]:
    from mikrot.app import app as cli_app

    result = CliRunner().invoke(cli_app, list(argv))
    return result.exit_code, result.stdout


def test_package_imports() -> None:
    import mikrot

    assert mikrot.__version__


def test_cli_version() -> None:
    code, out = _invoke("--version")
    assert code == 0
    assert "mikrot" in out


def test_manifest_json_parses() -> None:
    code, out = _invoke("--json", "manifest")
    assert code == 0
    data = json.loads(out)
    assert isinstance(data, dict)
    assert data["version"]
    assert isinstance(data["contract_version"], int)
    assert {c["path"][0] for c in data["commands"]} == {
        "doctor",
        "dhcp-leases",
        "make-static",
        "make-dynamic",
    }


def test_global_flag_hoisting() -> None:
    # `main()` rewrites argv so a global flag may appear after the subcommand:
    # `mikrot manifest --json` -> `mikrot --json manifest`.
    from mikrot.app import _hoist_global_flags

    assert _hoist_global_flags(["manifest", "--json"]) == ["--json", "manifest"]
    assert _hoist_global_flags(["dhcp-leases", "--mac", "00:15", "--json"]) == [
        "--json",
        "dhcp-leases",
        "--mac",
        "00:15",
    ]
