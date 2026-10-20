"""Synthetic precision and recall. Ground truth is read only in this evaluation module."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from veritas.decisions.service import evaluate_transaction
from veritas.evidence.keys import ensure_signing_key
from veritas.simulator.store import seed_database
from veritas.storage.db import apply_migrations, connect


def synthetic_report(db_path: Path, *, scoring_mode: str = "rule_only") -> dict[str, Any]:
    seed_database(db_path, seed=42, scale="tiny", replace=True, confirm_benchmark=False)
    with connect(db_path) as connection:
        apply_migrations(connection)
        positives = {
            row["transaction_id"]
            for row in connection.execute(
                """
                SELECT transaction_id FROM scenario_ground_truth
                WHERE transaction_id IS NOT NULL
                """
            )
            if row["transaction_id"] is not None
        }
        transaction_ids = [
            row["transaction_id"]
            for row in connection.execute(
                "SELECT transaction_id FROM transactions ORDER BY transaction_id"
            )
        ]
    signing_key = db_path.parent / "issuer.pem"
    ensure_signing_key(signing_key, "issuer-local-1")
    flagged: set[str] = set()
    for transaction_id in transaction_ids:
        decision = evaluate_transaction(
            db_path,
            transaction_id=transaction_id,
            idempotency_key=f"report-{transaction_id}",
            scoring_mode=scoring_mode,
            signing_key_path=signing_key,
            signing_key_id="issuer-local-1",
        )
        if decision["decision"] in {"REVIEW", "HIGH"}:
            flagged.add(transaction_id)
    true_positive = len(flagged & positives)
    false_positive = len(flagged - positives)
    false_negative = len(positives - flagged)
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    return {
        "dataset": "synthetic seed 42 tiny",
        "scoring_mode": scoring_mode,
        "score_kind": "experimental_score",
        "positives": len(positives),
        "flagged": len(flagged),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "caveat": (
            "These figures are from a synthetic seed-42 tiny scenario. "
            "They are not production bank-fraud accuracy, and the score is an "
            "experiment rather than a probability."
        ),
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)
