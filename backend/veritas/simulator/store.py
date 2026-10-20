"""Persist a generated dataset. Reseed deletes only project demo rows."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from veritas.simulator.generate import Dataset, build_dataset
from veritas.storage.db import apply_migrations, connect, transaction
from veritas.storage.queries import demo_rows_present, normalized_document

_DEMO_DELETE_ORDER = (
    "dataset_manifest",
    "scenario_ground_truth",
    "transactions",
    "accounts",
    "banks",
)


class ReseedRequired(Exception):
    pass


class DemoDataRetained(Exception):
    pass


def seed_database(
    db_path: Path,
    *,
    seed: int,
    scale: str,
    replace: bool,
    confirm_benchmark: bool,
) -> dict[str, object]:
    dataset = build_dataset(seed, scale, confirm_benchmark=confirm_benchmark)
    with connect(db_path) as connection:
        apply_migrations(connection)
        if demo_rows_present(connection) and not replace:
            raise ReseedRequired("demo data already exists")
        try:
            with transaction(connection):
                if replace and demo_rows_present(connection):
                    _delete_demo_rows(connection)
                _insert_dataset(connection, dataset)
        except sqlite3.IntegrityError as exc:
            raise DemoDataRetained("demo rows are still referenced") from exc
        stored = normalized_document(connection)
    return {
        "seed": dataset.seed,
        "scale": dataset.scale,
        "accounts": len(dataset.accounts),
        "transactions": len(dataset.transactions),
        "scenarios": ["mule-ring-fan", "pass-through-hops"],
        "replaced": replace,
        "content_sha256": dataset.content_sha256(),
        "stored_accounts": len(stored["accounts"]),
        "stored_transactions": len(stored["transactions"]),
    }


def _delete_demo_rows(connection: sqlite3.Connection) -> None:
    for table in _DEMO_DELETE_ORDER:
        connection.execute(f"DELETE FROM {table}")


def _insert_dataset(connection: sqlite3.Connection, dataset: Dataset) -> None:
    connection.executemany(
        "INSERT INTO banks (bank_id, display_name) VALUES (:bank_id, :display_name)",
        list(dataset.banks),
    )
    connection.executemany(
        """
        INSERT INTO accounts (account_id, bank_id, opened_at)
        VALUES (:account_id, :bank_id, :opened_at)
        """,
        list(dataset.accounts),
    )
    connection.executemany(
        """
        INSERT INTO transactions (
            transaction_id, from_account_id, to_account_id, amount_minor,
            event_time, currency, scenario_id
        ) VALUES (
            :transaction_id, :from_account_id, :to_account_id, :amount_minor,
            :event_time, :currency, :scenario_id
        )
        """,
        list(dataset.transactions),
    )
    connection.executemany(
        """
        INSERT INTO scenario_ground_truth (
            ground_truth_id, scenario_id, transaction_id, account_id, label
        ) VALUES (
            :ground_truth_id, :scenario_id, :transaction_id, :account_id, :label
        )
        """,
        list(dataset.ground_truth),
    )
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    connection.execute(
        """
        INSERT INTO dataset_manifest (
            manifest_id, seed, scale, account_count, transaction_count, content_sha256, created_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset.seed,
            dataset.scale,
            len(dataset.accounts),
            len(dataset.transactions),
            dataset.content_sha256(),
            created_at,
        ),
    )
