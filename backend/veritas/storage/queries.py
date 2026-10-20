"""Read models. Scoring queries never select ground-truth labels."""

from __future__ import annotations

import sqlite3
from typing import Any

PUBLIC_TRANSACTION_SQL = """
SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time, currency
FROM transactions
ORDER BY event_time, transaction_id
LIMIT ? OFFSET ?
"""

PUBLIC_TRANSACTION_COUNT_SQL = "SELECT COUNT(*) AS total FROM transactions"

SCORING_WINDOW_SQL = """
SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time, currency
FROM transactions
WHERE event_time <= ?
ORDER BY event_time, transaction_id
"""

SCORING_ONE_SQL = """
SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time, currency
FROM transactions
WHERE transaction_id = ?
"""


def public_transactions(
    connection: sqlite3.Connection, *, limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    total = int(connection.execute(PUBLIC_TRANSACTION_COUNT_SQL).fetchone()["total"])
    rows = connection.execute(PUBLIC_TRANSACTION_SQL, (limit, offset)).fetchall()
    return [_public_row(row) for row in rows], total


def scoring_window(connection: sqlite3.Connection, as_of: str) -> list[dict[str, Any]]:
    rows = connection.execute(SCORING_WINDOW_SQL, (as_of,)).fetchall()
    return [_public_row(row) for row in rows]


def scoring_transaction(
    connection: sqlite3.Connection, transaction_id: str
) -> dict[str, Any] | None:
    row = connection.execute(SCORING_ONE_SQL, (transaction_id,)).fetchone()
    if row is None:
        return None
    return _public_row(row)


def list_scenarios(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    manifest = connection.execute(
        """
        SELECT seed, scale, account_count, transaction_count, content_sha256, created_at
        FROM dataset_manifest
        WHERE manifest_id = 1
        """
    ).fetchone()
    scenarios: list[dict[str, Any]] = []
    if manifest is not None:
        scenarios.append(
            {
                "scenario_id": "dataset",
                "seed": int(manifest["seed"]),
                "scale": manifest["scale"],
                "account_count": int(manifest["account_count"]),
                "transaction_count": int(manifest["transaction_count"]),
                "content_sha256": manifest["content_sha256"],
                "created_at": manifest["created_at"],
            }
        )
    pattern_rows = connection.execute(
        """
        SELECT scenario_id, COUNT(*) AS ground_truth_rows
        FROM scenario_ground_truth
        GROUP BY scenario_id
        ORDER BY scenario_id
        """
    ).fetchall()
    for row in pattern_rows:
        scenarios.append(
            {
                "scenario_id": row["scenario_id"],
                "ground_truth_rows": int(row["ground_truth_rows"]),
            }
        )
    return scenarios


def demo_rows_present(connection: sqlite3.Connection) -> bool:
    count = connection.execute("SELECT COUNT(*) AS total FROM banks").fetchone()["total"]
    return int(count) > 0


def normalized_document(connection: sqlite3.Connection) -> dict[str, Any]:
    banks = [
        {"bank_id": row["bank_id"], "display_name": row["display_name"]}
        for row in connection.execute("SELECT bank_id, display_name FROM banks ORDER BY bank_id")
    ]
    accounts = [
        {
            "account_id": row["account_id"],
            "bank_id": row["bank_id"],
            "opened_at": row["opened_at"],
        }
        for row in connection.execute(
            "SELECT account_id, bank_id, opened_at FROM accounts ORDER BY account_id"
        )
    ]
    transactions = [
        {
            "transaction_id": row["transaction_id"],
            "from_account_id": row["from_account_id"],
            "to_account_id": row["to_account_id"],
            "amount_minor": int(row["amount_minor"]),
            "event_time": row["event_time"],
            "currency": row["currency"],
            "scenario_id": row["scenario_id"],
        }
        for row in connection.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, amount_minor,
                   event_time, currency, scenario_id
            FROM transactions
            ORDER BY transaction_id
            """
        )
    ]
    ground_truth = [
        {
            "ground_truth_id": row["ground_truth_id"],
            "scenario_id": row["scenario_id"],
            "transaction_id": row["transaction_id"],
            "account_id": row["account_id"],
            "label": row["label"],
        }
        for row in connection.execute(
            """
            SELECT ground_truth_id, scenario_id, transaction_id, account_id, label
            FROM scenario_ground_truth
            ORDER BY scenario_id, label, ground_truth_id
            """
        )
    ]
    return {
        "accounts": accounts,
        "banks": banks,
        "ground_truth": ground_truth,
        "transactions": transactions,
    }


def _public_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "transaction_id": row["transaction_id"],
        "from_account_id": row["from_account_id"],
        "to_account_id": row["to_account_id"],
        "amount_minor": int(row["amount_minor"]),
        "event_time": row["event_time"],
        "currency": row["currency"],
    }
