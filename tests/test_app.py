"""Tests for the root app: command alias resolution (AliasGroup)."""

from __future__ import annotations

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
