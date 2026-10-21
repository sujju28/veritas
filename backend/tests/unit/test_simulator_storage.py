"""Deterministic seed, storage integrity, and scenario API tests."""

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from veritas.api.app import create_app
from veritas.api.scenarios import TransactionItem
from veritas.api.settings import Settings
from veritas.decisions.requests import ScoringRequest
from veritas.simulator.generate import build_dataset, document_sha256
from veritas.simulator.scales import MAX_ACCOUNTS, MAX_TRANSACTIONS, resolve_scale
from veritas.simulator.store import seed_database
from veritas.simulator.validate import (
    PayloadError,
    validate_account_id,
    validate_amount_minor,
    validate_event_time,
)
from veritas.storage.db import apply_migrations, connect
from veritas.storage.queries import (
    PUBLIC_TRANSACTION_SQL,
    SCORING_WINDOW_SQL,
    normalized_document,
    scoring_window,
)

_LABELS = ("MULE_ACCOUNT", "FAN_IN_TRANSFER", "PASS_THROUGH_TRANSFER")


def _client(db_path: Path) -> TestClient:
    return TestClient(create_app(Settings(db_path=db_path)))


def test_default_seed_has_three_banks_300_accounts_and_2000_transactions(tmp_path: Path) -> None:
    first = tmp_path / "one.db"
    second = tmp_path / "two.db"
    left = seed_database(first, seed=42, scale="default", replace=False, confirm_benchmark=False)
    right = seed_database(second, seed=42, scale="default", replace=False, confirm_benchmark=False)
    assert left["accounts"] == 300
    assert left["transactions"] == 2000
    assert left["scenarios"] == ["mule-ring-fan", "pass-through-hops"]
    assert left["content_sha256"] == right["content_sha256"]
    with connect(first) as connection:
        banks = connection.execute("SELECT COUNT(*) AS total FROM banks").fetchone()["total"]
        accounts = connection.execute("SELECT COUNT(*) AS total FROM accounts").fetchone()["total"]
        transactions = connection.execute("SELECT COUNT(*) AS total FROM transactions").fetchone()[
            "total"
        ]
        labels = {
            row["scenario_id"]
            for row in connection.execute("SELECT DISTINCT scenario_id FROM scenario_ground_truth")
        }
        stored_hash = document_sha256(normalized_document(connection))
        issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    assert banks == 3
    assert accounts == 300
    assert transactions == 2000
    assert labels == {"mule-ring-fan", "pass-through-hops"}
    assert stored_hash == left["content_sha256"]
    assert issues == []
    assert journal == "wal"
    assert foreign_keys == 1


def test_reseed_replays_the_same_hash_and_requires_replace(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.db"
    original = seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    try:
        seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    except Exception as exc:
        assert type(exc).__name__ == "ReseedRequired"
    else:
        raise AssertionError("reseed without replace succeeded")
    replayed = seed_database(db_path, seed=42, scale="tiny", replace=True, confirm_benchmark=False)
    assert replayed["content_sha256"] == original["content_sha256"]
    assert replayed["accounts"] == 100
    assert replayed["transactions"] == 500


def test_planted_patterns_cross_banks_and_legitimate_rows_are_unlabeled(tmp_path: Path) -> None:
    db_path = tmp_path / "patterns.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    with connect(db_path) as connection:
        mule_bank = connection.execute(
            "SELECT bank_id FROM accounts WHERE account_id = 'acct-0000'"
        ).fetchone()["bank_id"]
        source_bank = connection.execute(
            "SELECT bank_id FROM accounts WHERE account_id = 'acct-0001'"
        ).fetchone()["bank_id"]
        destination_bank = connection.execute(
            "SELECT bank_id FROM accounts WHERE account_id = 'acct-0005'"
        ).fetchone()["bank_id"]
        hops = [
            row["bank_id"]
            for row in connection.execute(
                """
                SELECT bank_id FROM accounts
                WHERE account_id IN (
                    'acct-0009', 'acct-0010', 'acct-0011', 'acct-0012', 'acct-0013'
                )
                ORDER BY account_id
                """
            )
        ]
        labeled_transactions = connection.execute(
            """
            SELECT COUNT(*) AS total FROM scenario_ground_truth
            WHERE transaction_id IS NOT NULL
            """
        ).fetchone()["total"]
        legitimate = connection.execute(
            "SELECT COUNT(*) AS total FROM transactions WHERE scenario_id IS NULL"
        ).fetchone()["total"]
        leaked = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM transactions
            WHERE scenario_id IS NULL
              AND transaction_id IN (SELECT transaction_id FROM scenario_ground_truth)
            """
        ).fetchone()["total"]
    assert {mule_bank, source_bank, destination_bank} == {"BANK_A", "BANK_B", "BANK_C"}
    assert len(set(hops)) == 3
    assert labeled_transactions == 12
    assert legitimate == 488
    assert leaked == 0


def test_scoring_window_excludes_later_events(tmp_path: Path) -> None:
    db_path = tmp_path / "window.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    with connect(db_path) as connection:
        first_legit = connection.execute(
            """
            SELECT event_time FROM transactions
            WHERE scenario_id IS NULL
            ORDER BY event_time, transaction_id
            LIMIT 1
            """
        ).fetchone()["event_time"]
        visible = scoring_window(connection, first_legit)
        later = connection.execute(
            "SELECT COUNT(*) AS total FROM transactions WHERE event_time > ?",
            (first_legit,),
        ).fetchone()["total"]
    assert visible
    assert all(item["event_time"] <= first_legit for item in visible)
    assert later > 0
    assert len(visible) == 13
    assert "scenario_ground_truth" not in SCORING_WINDOW_SQL
    assert "label" not in SCORING_WINDOW_SQL
    assert "scenario_id" not in PUBLIC_TRANSACTION_SQL


def test_amounts_are_positive_integers_and_times_are_utc(tmp_path: Path) -> None:
    dataset = build_dataset(42, "tiny")
    amounts_ok = all(
        isinstance(item["amount_minor"], int) and item["amount_minor"] > 0
        for item in dataset.transactions
    )
    times_ok = all(
        item["event_time"].endswith("Z") and "+" not in item["event_time"]
        for item in dataset.transactions
    )
    assert amounts_ok
    assert times_ok
    assert all(item["opened_at"].endswith("Z") for item in dataset.accounts)
    assert validate_amount_minor(150_000) == 150_000
    for value in (1.5, True, 0, -20, "150000"):
        try:
            validate_amount_minor(value)
        except PayloadError:
            continue
        raise AssertionError(f"accepted amount {value!r}")
    for value in ("2026-01-15T09:00:00+05:30", "2026-01-15T09:00:00", "yesterday"):
        try:
            validate_event_time(value)
        except PayloadError:
            continue
        raise AssertionError(f"accepted time {value!r}")
    try:
        validate_account_id("Jane Doe")
    except PayloadError:
        return
    raise AssertionError("accepted a personal account name")


def test_scale_guard_rejects_benchmark_and_oversized_counts() -> None:
    assert resolve_scale("default", confirm_benchmark=False) == (300, 2_000)
    assert MAX_ACCOUNTS == 1_000
    assert MAX_TRANSACTIONS == 10_000
    try:
        resolve_scale("benchmark", confirm_benchmark=False)
    except Exception as exc:
        assert type(exc).__name__ == "BenchmarkConfirmationRequired"
    else:
        raise AssertionError("benchmark ran without confirmation")
    assert resolve_scale("benchmark", confirm_benchmark=True) == (1_000, 10_000)


def test_invalid_payload_does_not_write_and_reseed_keeps_downstream_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "api.db"
    with _client(db_path) as client:
        rejected = client.post(
            "/api/v1/scenarios/generate",
            json={
                "seed": 42,
                "scale": "tiny",
                "account_id": "Jane Doe",
                "amount_minor": 1.5,
                "event_time": "2026-01-15T09:00:00+05:30",
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
        assert not db_path.exists()

        created = client.post("/api/v1/scenarios/generate", json={"seed": 42, "scale": "tiny"})
        assert created.status_code == 200
        body = created.json()
        assert body["accounts"] == 100
        assert body["transactions"] == 500
        before = body["content_sha256"]

        again = client.post("/api/v1/scenarios/generate", json={"seed": 42, "scale": "tiny"})
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "RESEED_REQUIRED"

        huge = client.post(
            "/api/v1/scenarios/generate",
            json={"seed": 42, "scale": "huge", "replace": True},
        )
        assert huge.status_code == 400
        benchmark = client.post(
            "/api/v1/scenarios/generate",
            json={"seed": 42, "scale": "benchmark", "replace": True},
        )
        assert benchmark.status_code == 400
        assert benchmark.json()["error"]["code"] == "CONFIRM_BENCHMARK_REQUIRED"

        page = client.get("/api/v1/transactions?limit=101")
        assert page.status_code == 422
        negative = client.get("/api/v1/transactions?offset=-1")
        assert negative.status_code == 422

    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO decisions (
                decision_id, idempotency_key, transaction_id, risk_score, decision_category,
                reason_codes, model_version, ruleset_version, created_at
            ) VALUES ('dec-1', 'idem-1', 'txn-000000', 10, 'REVIEW', '[]', 'none', 'none',
                      '2026-01-15T09:00:00Z')
            """
        )
    with _client(db_path) as client:
        blocked = client.post(
            "/api/v1/scenarios/generate",
            json={"seed": 42, "scale": "tiny", "replace": True},
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "DEMO_DATA_RETAINED"
        listed = client.get("/api/v1/transactions?limit=2")
        scenarios = client.get("/api/v1/scenarios")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 500
    assert set(payload["items"][0]) == set(TransactionItem.model_fields)
    raw = json.dumps(payload)
    assert "MULE_ACCOUNT" not in raw
    assert "label" not in raw
    scenario_raw = json.dumps(scenarios.json())
    for label in _LABELS:
        assert label not in scenario_raw
    assert "mule-ring-fan" in scenario_raw
    assert "pass-through-hops" in scenario_raw
    with connect(db_path) as connection:
        assert document_sha256(normalized_document(connection)) == before
        decisions = connection.execute("SELECT COUNT(*) AS total FROM decisions").fetchone()[
            "total"
        ]
    assert decisions == 1
    assert "label" not in ScoringRequest.model_fields
    assert set(ScoringRequest.model_fields) == {"transaction_id", "idempotency_key"}


def test_migrations_record_one_version(tmp_path: Path) -> None:
    db_path = tmp_path / "migrate.db"
    with connect(db_path) as connection:
        first = apply_migrations(connection)
        second = apply_migrations(connection)
        versions = connection.execute("SELECT version FROM schema_migrations").fetchall()
    assert first == ["001_initial", "002_decision_explain", "003_ruleset_version", "004_onchain"]
    assert second == []
    assert [row["version"] for row in versions] == [
        "001_initial",
        "002_decision_explain",
        "003_ruleset_version",
        "004_onchain",
    ]
    try:
        with connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO transactions (
                    transaction_id, from_account_id, to_account_id,
                    amount_minor, event_time, currency
                ) VALUES (
                    'txn-x', 'acct-9999', 'acct-9998', 10, '2026-01-15T09:00:00Z', 'USD'
                )
                """
            )
    except sqlite3.IntegrityError:
        return
    raise AssertionError("transaction without accounts was stored")
