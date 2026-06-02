"""Tests for secretref: provider matching, CLI resolution, env provider, config.

The external CLI is never really invoked: ``shutil.which`` and ``subprocess.run``
are monkeypatched in the providers module. The env provider runs in-process
(real ``expandvars``) against a monkeypatched environment.
"""

from __future__ import annotations

import subprocess

import pytest

import mikrot.secretref.providers as providers_mod
from mikrot.secretref import (
    CliProvider,
    EnvProvider,
    SecretResolutionError,
    active_providers,
    provider_for,
    providers_from_env,
    resolve_mapping,
    resolve_value,
)


class _FakeCompleted:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_op(monkeypatch: pytest.MonkeyPatch, completed: _FakeCompleted) -> None:
    monkeypatch.setattr(providers_mod.shutil, "which", lambda _tool: "/usr/bin/op")
    monkeypatch.setattr(providers_mod.subprocess, "run", lambda *a, **k: completed)


# --- CLI provider ---


def test_provider_for_matches_op_prefix() -> None:
    provider = provider_for("op://Vault/Item/field")
    assert isinstance(provider, CliProvider)
    assert provider.tool == "op"
    assert provider_for("plain-secret") is None


def test_argv_appends_ref_without_placeholder() -> None:
    assert CliProvider("op://", "op", ("read",)).argv("op://X") == ["op", "read", "op://X"]


def test_argv_substitutes_ref_placeholder() -> None:
    provider = CliProvider("bw://", "bw", ("get", "password", "{ref}"))
    assert provider.argv("bw://item") == ["bw", "get", "password", "bw://item"]


def test_non_reference_passes_through() -> None:
    assert resolve_value("plain-secret") == "plain-secret"


def test_reference_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_op(monkeypatch, _FakeCompleted(returncode=0, stdout="s3cret\n"))
    assert resolve_value("op://V/I/f") == "s3cret"


def test_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers_mod.shutil, "which", lambda _tool: None)
    with pytest.raises(SecretResolutionError) as excinfo:
        resolve_value("op://V/I/f")
    assert excinfo.value.tool == "op"
    assert excinfo.value.ref == "op://V/I/f"


def test_nonzero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_op(monkeypatch, _FakeCompleted(returncode=1, stderr="not signed in"))
    with pytest.raises(SecretResolutionError):
        resolve_value("op://V/I/f")


def test_empty_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_op(monkeypatch, _FakeCompleted(returncode=0, stdout="\n"))
    with pytest.raises(SecretResolutionError):
        resolve_value("op://V/I/f")


def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers_mod.shutil, "which", lambda _tool: "/usr/bin/op")

    def _raise(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="op", timeout=1.0)

    monkeypatch.setattr(providers_mod.subprocess, "run", _raise)
    with pytest.raises(SecretResolutionError):
        resolve_value("op://V/I/f")


def test_resolve_mapping_mixed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_op(monkeypatch, _FakeCompleted(returncode=0, stdout="resolved\n"))
    out = resolve_mapping({"A": "op://x", "B": "plain", "C": "192.168.88.1"})
    assert out == {"A": "resolved", "B": "plain", "C": "192.168.88.1"}


# --- env provider (example custom provider) ---


def test_provider_for_matches_env_prefix() -> None:
    assert isinstance(provider_for("env://${X}"), EnvProvider)


def test_env_provider_uses_existing_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PORT", "9999")
    assert resolve_value("env://${APP_PORT}") == "9999"


def test_env_provider_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_PORT", raising=False)
    assert resolve_value("env://${APP_PORT:-8080}") == "8080"


def test_env_provider_undefined_without_default_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEFINITELY_UNSET_VAR", raising=False)
    with pytest.raises(SecretResolutionError):
        resolve_value("env://${DEFINITELY_UNSET_VAR}")


# --- SECRETREF_PROVIDERS (JSON env extension) ---

_BW_JSON = '[{"prefix":"bw://","tool":"bw","args":["get","password","{ref}"]}]'


def test_providers_from_env_empty() -> None:
    assert providers_from_env({}) == ()


def test_providers_from_env_parses_json() -> None:
    providers = providers_from_env({"SECRETREF_PROVIDERS": _BW_JSON})
    assert providers == (CliProvider("bw://", "bw", ("get", "password", "{ref}")),)


def test_active_providers_env_first_then_builtins() -> None:
    active = active_providers({"SECRETREF_PROVIDERS": _BW_JSON})
    assert active[0].prefix == "bw://"                 # env provider first
    prefixes = [p.prefix for p in active]
    assert "op://" in prefixes and "env://" in prefixes  # built-ins still present


def test_env_provider_overrides_builtin_prefix() -> None:
    custom = '[{"prefix":"op://","tool":"myop","args":["fetch"]}]'
    provider = provider_for("op://X", active_providers({"SECRETREF_PROVIDERS": custom}))
    assert isinstance(provider, CliProvider) and provider.tool == "myop"


def test_provider_for_picks_env_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETREF_PROVIDERS", _BW_JSON)
    provider = provider_for("bw://item")               # no explicit providers -> reads env
    assert isinstance(provider, CliProvider) and provider.tool == "bw"


def test_invalid_json_raises() -> None:
    with pytest.raises(SecretResolutionError):
        providers_from_env({"SECRETREF_PROVIDERS": "not json"})


def test_missing_required_fields_raises() -> None:
    with pytest.raises(SecretResolutionError):
        providers_from_env({"SECRETREF_PROVIDERS": '[{"prefix":"bw://"}]'})


def test_non_array_raises() -> None:
    with pytest.raises(SecretResolutionError):
        providers_from_env({"SECRETREF_PROVIDERS": '{"prefix":"bw://"}'})
