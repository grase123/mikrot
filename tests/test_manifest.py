"""Tests for the hand-written manifest: shape + code consistency.

This is the deliberately lightweight check (no heavy contract/drift
machinery): it asserts that every code named in the manifest is a real
registered ``ERROR_CODES`` member, that per-command ``error_codes`` stay
domain-only (infrastructure codes apply globally), and that the hand-written
``fields`` maps match the real Pydantic ``model_fields`` so they cannot drift.
"""

from __future__ import annotations

from mikrot.commands.manifest import CONTRACT_VERSION, build_manifest
from mikrot.diagnostics import CheckResult, DoctorEnvelope
from mikrot.errors import _EXIT_CODES, ERROR_CODES, MikrotError
from mikrot.models import LeaseActionEnvelope

# Documented model name -> the Pydantic class it must stay in sync with.
# (``Lease`` is a RouterOS passthrough with no model, so it is excluded.)
_MODEL_CLASSES = {
    "DoctorEnvelope": DoctorEnvelope,
    "LeaseActionEnvelope": LeaseActionEnvelope,
    "CheckResult": CheckResult,
}


def test_top_level_shape() -> None:
    manifest = build_manifest()
    assert set(manifest) == {
        "version",
        "contract_version",
        "commands",
        "models",
        "error_shape",
        "infrastructure_errors",
        "exit_codes",
    }
    assert manifest["contract_version"] == CONTRACT_VERSION
    assert manifest["version"]


def test_each_command_entry_is_well_formed() -> None:
    for command in build_manifest()["commands"]:
        assert command["path"] and isinstance(command["path"], list)
        assert command["summary"]
        shape = command["response_shape"]
        assert shape["kind"] in {"model", "list"}
        assert shape["model"]
        assert isinstance(shape["fields"], dict) and shape["fields"]
        assert isinstance(command["error_codes"], list)


def test_all_manifest_codes_are_registered() -> None:
    manifest = build_manifest()
    for code in manifest["infrastructure_errors"]:
        assert code in ERROR_CODES, code
    for command in manifest["commands"]:
        for code in command["error_codes"]:
            assert code in ERROR_CODES, code


def test_per_command_error_codes_are_domain_only() -> None:
    # Decision: per-command error_codes list only domain-specific codes;
    # infrastructure codes apply globally and must not be duplicated.
    manifest = build_manifest()
    infra = set(manifest["infrastructure_errors"])
    for command in manifest["commands"]:
        assert not (set(command["error_codes"]) & infra), command["path"]


def test_doctor_is_errors_as_data() -> None:
    doctor = next(c for c in build_manifest()["commands"] if c["path"] == ["doctor"])
    assert doctor["error_codes"] == []


def test_model_fields_match_pydantic() -> None:
    # The hand-written `fields` keys must equal the real model_fields so the
    # manifest cannot silently drift from the models.
    manifest = build_manifest()
    documented: dict[str, set[str]] = {}
    for command in manifest["commands"]:
        shape = command["response_shape"]
        if not shape.get("passthrough"):
            documented.setdefault(shape["model"], set(shape["fields"]))
    for name, shape in manifest["models"].items():
        documented[name] = set(shape["fields"])
    for name, cls in _MODEL_CLASSES.items():
        assert documented[name] == set(cls.model_fields), name


def test_error_shape_matches_envelope() -> None:
    manifest = build_manifest()
    envelope = MikrotError("boom", code="unknown").as_envelope()
    assert set(manifest["error_shape"]["fields"]) == set(envelope)


def test_secret_resolution_failed_is_infrastructure() -> None:
    assert "secret_resolution_failed" in build_manifest()["infrastructure_errors"]


def test_exit_codes_cover_registered_codes() -> None:
    # The published code->exit map must cover exactly the registered codes and
    # mirror the single source of truth (errors._EXIT_CODES).
    exits = build_manifest()["exit_codes"]
    assert set(exits) == set(ERROR_CODES)
    assert all(isinstance(v, int) for v in exits.values())
    assert exits == _EXIT_CODES
