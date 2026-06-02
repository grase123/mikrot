"""Tests for settings: defaults, base_url, password enforcement, .env loading.

Suite-wide isolation lives in ``conftest.py`` (``_load_env`` is a no-op and
``os.environ`` is restored after each test). The loader tests here re-install
the real ``_load_env`` (captured at import time, before the autouse patch) and
point ``MIKROT_CONFIG_HOME`` at a tmp dir, so the real create/load logic runs
without ever touching the developer's home or the repo's real ``.env``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import mikrot.settings as settings_mod
from mikrot.errors import MikrotError
from mikrot.secretref import SecretResolutionError
from mikrot.settings import Settings, load_settings

# Captured before conftest's autouse fixture patches the module attribute.
_REAL_LOAD_ENV = settings_mod._load_env


def test_default_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIKROT_PASSWORD", raising=False)
    s = Settings(password="x")
    assert s.host == "192.168.88.1"
    assert s.port == 80
    assert s.scheme == "http"
    assert s.user == "admin"
    assert s.timeout == 5.0
    assert s.base_url == "http://192.168.88.1:80/rest"


def test_load_settings_requires_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MIKROT_PASSWORD", raising=False)
    with pytest.raises(MikrotError) as excinfo:
        load_settings()
    assert excinfo.value.code == "config_missing"
    assert excinfo.value.exit_code == 1


def test_load_settings_ok_with_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROT_PASSWORD", "secret")
    s = load_settings()
    assert s.password == "secret"


def test_env_prefix_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROT_PASSWORD", "secret")
    monkeypatch.setenv("MIKROT_HOST", "10.0.0.1")
    monkeypatch.setenv("MIKROT_PORT", "443")
    monkeypatch.setenv("MIKROT_SCHEME", "https")
    s = load_settings()
    assert s.base_url == "https://10.0.0.1:443/rest"


# --- global .env scaffold + MIKROT_CONFIG_HOME ---


def test_global_env_created_and_fully_commented(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("MIKROT_CONFIG_HOME", str(cfg))
    path = settings_mod._ensure_global_env()
    assert path == cfg / ".env"
    assert path.exists()
    # Every non-blank line is a comment: the scaffold sets nothing by itself.
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        assert stripped == "" or stripped.startswith("#")


def test_global_env_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    existing = cfg / ".env"
    existing.write_text("MIKROT_HOST=keepme\n", encoding="utf-8")
    monkeypatch.setenv("MIKROT_CONFIG_HOME", str(cfg))
    settings_mod._ensure_global_env()
    assert existing.read_text(encoding="utf-8") == "MIKROT_HOST=keepme\n"


def test_precedence_cwd_over_global(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("MIKROT_HOST=globalhost\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / ".env").write_text("MIKROT_HOST=cwdhost\n", encoding="utf-8")
    monkeypatch.setenv("MIKROT_CONFIG_HOME", str(cfg))
    monkeypatch.chdir(work)
    monkeypatch.delenv("MIKROT_HOST", raising=False)
    _REAL_LOAD_ENV()
    assert Settings().host == "cwdhost"


def test_precedence_shell_over_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("MIKROT_HOST=globalhost\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / ".env").write_text("MIKROT_HOST=cwdhost\n", encoding="utf-8")
    monkeypatch.setenv("MIKROT_CONFIG_HOME", str(cfg))
    monkeypatch.chdir(work)
    monkeypatch.setenv("MIKROT_HOST", "shellhost")
    _REAL_LOAD_ENV()
    assert Settings().host == "shellhost"


def test_global_used_when_no_cwd_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_text("MIKROT_HOST=globalhost\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()  # no .env here
    monkeypatch.setenv("MIKROT_CONFIG_HOME", str(cfg))
    monkeypatch.chdir(work)
    monkeypatch.delenv("MIKROT_HOST", raising=False)
    _REAL_LOAD_ENV()
    assert Settings().host == "globalhost"


# --- secret references (secretref / op://) ---


def test_secret_ref_resolved_into_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROT_PASSWORD", "op://V/I/field")
    monkeypatch.setattr(
        settings_mod,
        "resolve_mapping",
        lambda mapping: {**mapping, "MIKROT_PASSWORD": "resolved-secret"},
    )
    settings_mod._resolve_secret_refs()
    assert os.environ["MIKROT_PASSWORD"] == "resolved-secret"


def test_secret_ref_failure_becomes_mikrot_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIKROT_PASSWORD", "op://V/I/field")

    def _boom(_mapping: dict[str, str]) -> dict[str, str]:
        raise SecretResolutionError("nope", ref="op://V/I/field", tool="op")

    monkeypatch.setattr(settings_mod, "resolve_mapping", _boom)
    with pytest.raises(MikrotError) as excinfo:
        settings_mod._resolve_secret_refs()
    assert excinfo.value.code == "secret_resolution_failed"
    assert excinfo.value.exit_code == 1
    assert excinfo.value.context["ref"] == "op://V/I/field"
