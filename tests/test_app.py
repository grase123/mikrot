"""Tests for the root app: command alias resolution (AliasGroup)."""

from __future__ import annotations

from typer.main import get_command
from typer.testing import CliRunner

from mikrot.app import app


def test_command_aliases_resolve_to_dhcp_leases() -> None:
    runner = CliRunner()
    for alias in ("l", "d"):
        result = runner.invoke(app, [alias, "--help"])
        assert result.exit_code == 0, alias
        # The resolved command's help body lists dhcp-leases options.
        assert "--comment" in result.output, alias


def test_unknown_command_still_errors() -> None:
    result = CliRunner().invoke(app, ["definitely-not-a-command"])
    assert result.exit_code != 0


def test_dhcp_leases_filter_option_aliases() -> None:
    # Introspect the built command's option flags (robust vs parsing help text).
    leases = get_command(app).commands["dhcp-leases"]  # type: ignore[attr-defined]
    flags = {flag for param in leases.params for flag in param.opts}
    expected = {
        "--mac", "-m",
        "--name", "--host", "-n",
        "--status", "-s",
        "--comment", "-c",
        "--address", "--ip", "-a", "-i",
    }
    assert expected <= flags, expected - flags


def test_dash_h_shows_help() -> None:
    runner = CliRunner()
    for argv in (["-h"], ["dhcp-leases", "-h"]):
        result = runner.invoke(app, argv)
        assert result.exit_code == 0, argv
        assert "Usage" in result.output, argv
