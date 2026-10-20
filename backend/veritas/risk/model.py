"""Optional IsolationForest. Fit once on a legitimate training partition."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from veritas.graph.features import feature_snapshot
from veritas.graph.window import Transfer

MODEL_VERSION = "iforest-v1"
TRAINING_SEED = 7
_IMPUTE = 0.0
_NUMERIC = (
    "src_in_count_15m",
    "src_out_count_15m",
    "src_in_count_1h",
    "src_out_count_1h",
    "dst_in_count_15m",
    "dst_out_count_15m",
    "dst_in_count_1h",
    "dst_out_count_1h",
    "src_amount_out_15m",
    "src_amount_out_1h",
    "dst_amount_in_15m",
    "dst_amount_in_1h",
    "src_fan_out_15m",
    "dst_fan_in_15m",
    "src_onward_ratio_15m",
    "src_upstream_hops",
    "window_edge_count",
)

_cache: dict[str, Any] | None = None
_cache_path: str | None = None


def reset_model_cache() -> None:
    global _cache, _cache_path
    _cache = None
    _cache_path = None


def vector(features: dict[str, Any]) -> list[float]:
    values: list[float] = []
    for name in _NUMERIC:
        raw = features.get(name)
        if name == "src_onward_ratio_15m" and raw is None:
            values.append(_IMPUTE)
            values.append(1.0)
        elif name == "src_onward_ratio_15m":
            values.append(float(raw))
            values.append(0.0)
        else:
            values.append(float(raw or 0))
    return values


def train_model(path: Path, *, seed: int = TRAINING_SEED, rows: int = 240) -> dict[str, Any]:
    """Train on synthetic legitimate transfers only. Does not read ground truth."""
    try:
        from sklearn.ensemble import IsolationForest
    except ImportError as exc:
        raise RuntimeError("sklearn_unavailable") from exc

    population = _legitimate_population(seed=seed, rows=rows)
    matrix = [_features_for_row(population, index) for index in range(len(population))]
    model = IsolationForest(
        n_estimators=40,
        max_samples=64,
        random_state=seed,
        contamination="auto",
        n_jobs=1,
    )
    model.fit(matrix)
    raw_scores = [-float(value) for value in model.decision_function(matrix)]
    ordered = sorted(raw_scores)
    p05 = _percentile(ordered, 0.05)
    p95 = _percentile(ordered, 0.95)
    path.parent.mkdir(parents=True, exist_ok=True)
    import joblib

    joblib.dump(model, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    metadata = {
        "model_version": MODEL_VERSION,
        "training_seed": seed,
        "training_rows": rows,
        "norm_p05": p05,
        "norm_p95": p95,
        "impute_value": _IMPUTE,
        "artifact_sha256": digest,
        "feature_names": list(_NUMERIC) + ["src_onward_ratio_missing"],
    }
    path.with_suffix(".json").write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    reset_model_cache()
    return metadata


def load_model(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    global _cache, _cache_path
    if path is None or not path.is_file():
        return None, "model_not_configured"
    key = str(path.resolve())
    if _cache is not None and _cache_path == key:
        return _cache, None
    try:
        import joblib
    except ImportError:
        return None, "sklearn_unavailable"
    metadata_path = path.with_suffix(".json")
    if not metadata_path.is_file():
        return None, "model_metadata_missing"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != metadata.get("artifact_sha256"):
        return None, "model_hash_mismatch"
    try:
        model = joblib.load(path)
    except ImportError:
        return None, "sklearn_unavailable"
    loaded = {"model": model, "metadata": metadata}
    _cache = loaded
    _cache_path = key
    return loaded, None


def normalized_anomaly(loaded: dict[str, Any], features: dict[str, Any]) -> int | None:
    metadata = loaded["metadata"]
    low = float(metadata["norm_p05"])
    high = float(metadata["norm_p95"])
    if high - low < 1e-9:
        return None
    raw = -float(loaded["model"].decision_function([vector(features)])[0])
    scaled = round(100 * (raw - low) / (high - low))
    return min(max(scaled, 0), 100)


def _features_for_row(population: list[Transfer], index: int) -> list[float]:
    subject = population[index]
    window = population[: index + 1]
    snapshot = feature_snapshot(
        window,
        transaction_id=subject.transaction_id,
        source=subject.from_account_id,
        destination=subject.to_account_id,
        as_of=subject.event_time,
        truncated=False,
    )
    return vector(snapshot["features"])


def _legitimate_population(*, seed: int, rows: int) -> list[Transfer]:
    rng = random.Random(seed)
    accounts = [f"trn-{index:04d}" for index in range(40)]
    base = datetime(2026, 2, 1, tzinfo=UTC)
    population: list[Transfer] = []
    for index in range(rows):
        source = rng.choice(accounts)
        destination = rng.choice(accounts)
        while destination == source:
            destination = rng.choice(accounts)
        population.append(
            Transfer(
                transaction_id=f"train-{index:06d}",
                from_account_id=source,
                to_account_id=destination,
                amount_minor=rng.randrange(1_000, 80_000),
                event_time=(base + timedelta(seconds=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        )
    return population


def _percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight
