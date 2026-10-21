"""Tests for ruleset manifest generation, drift checking, and hash stability (RSR-01)."""

from __future__ import annotations

import json
from pathlib import Path

from veritas.risk.manifest import (
    build_ruleset_manifest,
    ruleset_manifest_bytes,
    ruleset_manifest_sha256,
)
from veritas.risk.manifest import (
    main as manifest_main,
)
from veritas.risk.rules import _RULES, RULESET_VERSION

PINNED_V1_HASH = "5cfa632b5379cfb776d6bc0ddfe13ad40c3afb8582239c5c5d675555c4b1b655"


def test_manifest_matches_declared_rules() -> None:
    manifest = build_ruleset_manifest()
    assert manifest["ruleset_version"] == RULESET_VERSION
    assert len(manifest["rules"]) == len(_RULES)
    for rule, (code, feat, thresh, pts) in zip(manifest["rules"], _RULES, strict=True):
        assert rule["code"] == code
        assert rule["feature"] == feat
        assert rule["threshold"] == thresh
        assert rule["points"] == pts


def test_manifest_sha256_stability() -> None:
    manifest = build_ruleset_manifest()
    digest = ruleset_manifest_sha256(manifest)
    assert digest == PINNED_V1_HASH
    # Recomputing produces identical canonical bytes
    assert ruleset_manifest_bytes(manifest) == ruleset_manifest_bytes()


def test_manifest_file_drift() -> None:
    manifest_path = Path(__file__).resolve().parents[3] / "docs" / "rulesets" / "rules-v1.json"
    assert manifest_path.exists(), f"Published manifest missing at {manifest_path}"
    file_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    file_digest = ruleset_manifest_sha256(file_data)
    live_digest = ruleset_manifest_sha256()
    assert file_digest == live_digest == PINNED_V1_HASH


def test_mutating_threshold_changes_hash_rsr_01() -> None:
    base_manifest = build_ruleset_manifest()
    base_hash = ruleset_manifest_sha256(base_manifest)

    # Mutate a single threshold in the rules tuple
    mutated_rules = list(_RULES)
    code, feat, thresh, pts = mutated_rules[0]
    mutated_rules[0] = (code, feat, thresh + 1.0, pts)
    mutated_manifest = build_ruleset_manifest(rules=tuple(mutated_rules))
    mutated_hash = ruleset_manifest_sha256(mutated_manifest)

    assert mutated_hash != base_hash


def test_mutating_points_or_version_changes_hash() -> None:
    base_hash = ruleset_manifest_sha256()

    # Change points
    mutated_rules = list(_RULES)
    code, feat, thresh, pts = mutated_rules[0]
    mutated_rules[0] = (code, feat, thresh, pts + 5)
    pts_hash = ruleset_manifest_sha256(build_ruleset_manifest(rules=tuple(mutated_rules)))
    assert pts_hash != base_hash

    # Change version
    ver_hash = ruleset_manifest_sha256(build_ruleset_manifest(version="rules-v2"))
    assert ver_hash != base_hash


def test_manifest_cli_check(tmp_path: Path) -> None:
    manifest_path = Path(__file__).resolve().parents[3] / "docs" / "rulesets" / "rules-v1.json"
    # Valid file check returns 0
    assert manifest_main(["--check", str(manifest_path)]) == 0

    # Tampered file check returns 1
    tampered_file = tmp_path / "tampered-rules.json"
    content = json.loads(manifest_path.read_text(encoding="utf-8"))
    content["rules"][0]["threshold"] = 999.0
    tampered_file.write_text(json.dumps(content), encoding="utf-8")
    assert manifest_main(["--check", str(tampered_file)]) == 1
