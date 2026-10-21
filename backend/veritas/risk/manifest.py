"""Ruleset manifest generator and hash computation.

Covers declared parameters:
- ruleset version
- rule table (code, feature, threshold, points)
- decision bands (LOW, REVIEW, HIGH score ranges)
- score combination specification

Does NOT hash arbitrary Python source code or AST.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from veritas.evidence.canonical import canonical_bytes
from veritas.risk.rules import _RULES, RULESET_VERSION

DEFAULT_BANDS: list[dict[str, Any]] = [
    {"band": "LOW", "min_score": 0, "max_score": 39},
    {"band": "REVIEW", "min_score": 40, "max_score": 69},
    {"band": "HIGH", "min_score": 70, "max_score": 100},
]

DEFAULT_COMBINATION: dict[str, Any] = {
    "formula": "(6 * ml_normalized + 4 * rule_score + 5) // 10",
    "ml_weight": 0.6,
    "rule_weight": 0.4,
    "rounding": "floor_with_half_up_via_plus_5",
}


def build_ruleset_manifest(
    *,
    version: str | None = None,
    rules: tuple[tuple[str, str, float, int], ...] | None = None,
    bands: list[dict[str, Any]] | None = None,
    combination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_version = version if version is not None else RULESET_VERSION
    active_rules = rules if rules is not None else _RULES
    active_bands = bands if bands is not None else DEFAULT_BANDS
    active_combination = combination if combination is not None else DEFAULT_COMBINATION

    return {
        "ruleset_version": active_version,
        "score_combination": active_combination,
        "decision_bands": active_bands,
        "rules": [
            {
                "code": code,
                "feature": feature,
                "threshold": threshold,
                "points": points,
            }
            for code, feature, threshold, points in active_rules
        ],
    }


def ruleset_manifest_bytes(manifest: dict[str, Any] | None = None) -> bytes:
    if manifest is None:
        manifest = build_ruleset_manifest()
    return canonical_bytes(manifest)


def ruleset_manifest_sha256(manifest: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(ruleset_manifest_bytes(manifest)).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m veritas.risk.manifest",
        description="Generate or verify the canonical ruleset manifest",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to write the ruleset manifest JSON file",
    )
    parser.add_argument(
        "--check",
        "-c",
        type=Path,
        help="Check that the given file matches the generated manifest",
    )
    parser.add_argument(
        "--hash-only",
        action="store_true",
        help="Print only the SHA-256 digest of the canonical manifest",
    )
    args = parser.parse_args(argv)

    manifest = build_ruleset_manifest()
    digest = ruleset_manifest_sha256(manifest)

    if args.hash_only:
        print(digest)
        return 0

    if args.check:
        if not args.check.exists():
            print(f"File not found: {args.check}", file=sys.stderr)
            return 1
        existing_text = args.check.read_text(encoding="utf-8")
        try:
            existing_data = json.loads(existing_text)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in {args.check}: {exc}", file=sys.stderr)
            return 1
        existing_digest = ruleset_manifest_sha256(existing_data)
        if existing_digest != digest:
            print(
                f"Manifest drift detected! File has digest {existing_digest}, "
                f"generated has {digest}",
                file=sys.stderr,
            )
            return 1
        print(f"Manifest matches {args.check} ({digest})")
        return 0

    formatted = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(formatted, encoding="utf-8")
        print(f"Wrote manifest to {args.output} (sha256: {digest})")
    else:
        sys.stdout.write(formatted)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
