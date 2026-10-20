"""Versioned rules. A reason code is emitted only when its feature clears the threshold."""

from __future__ import annotations

from typing import Any

RULESET_VERSION = "rules-v1"

_RULES: tuple[tuple[str, str, float, int], ...] = (
    ("FAN_IN", "dst_fan_in_15m", 4, 40),
    ("FAN_OUT", "src_fan_out_15m", 4, 40),
    ("HIGH_VELOCITY", "src_out_count_15m", 4, 25),
    ("HIGH_VELOCITY", "dst_in_count_15m", 4, 25),
    ("RAPID_ONWARD", "src_onward_ratio_15m", 0.8, 35),
    ("MULTI_HOP", "src_upstream_hops", 3, 20),
)


def apply_rules(features: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    triggered: list[dict[str, Any]] = []
    seen: set[str] = set()
    score = 0
    for code, feature, threshold, points in _RULES:
        value = features.get(feature)
        if value is None or float(value) < threshold:
            continue
        if code not in seen:
            score += points
            seen.add(code)
        triggered.append(
            {
                "code": code,
                "feature": feature,
                "value": value,
                "threshold": threshold,
            }
        )
    return min(score, 100), triggered


def decision_band(score: int) -> str:
    if score <= 39:
        return "LOW"
    if score <= 69:
        return "REVIEW"
    return "HIGH"


def combine_scores(rule_score: int, ml_normalized: int | None) -> tuple[int, str]:
    """Experimental score. This is not a probability."""
    if ml_normalized is None:
        return rule_score, "rule_only"
    mixed = (6 * ml_normalized + 4 * rule_score + 5) // 10
    return min(max(mixed, 0), 100), "hybrid_experimental"
