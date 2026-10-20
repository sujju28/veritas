"""Graph leakage, planted-pattern reasons, idempotency, and the experimental score."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from veritas.api.app import create_app
from veritas.api.settings import Settings
from veritas.evidence.keys import ensure_signing_key
from veritas.graph.features import bounded_subgraph, feature_snapshot
from veritas.graph.window import Transfer, load_window
from veritas.risk.model import train_model
from veritas.risk.report import synthetic_report
from veritas.risk.rules import combine_scores, decision_band
from veritas.simulator.store import seed_database
from veritas.storage.db import connect

_FORBIDDEN = {"label", "ground_truth", "scenario_id", "MULE_ACCOUNT"}


def _client(db_path: Path, **kwargs: object) -> TestClient:
    key_path = db_path.parent / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    settings = Settings(
        db_path=db_path,
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
        **kwargs,
    )
    return TestClient(create_app(settings))


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        for item in value.values():
            found.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


def test_window_excludes_future_transfers(tmp_path: Path) -> None:
    db_path = tmp_path / "future.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    early = feature_snapshot(
        [
            Transfer("t1", "acct-0001", "acct-0000", 150_000, "2026-01-15T09:00:00Z"),
        ],
        transaction_id="t1",
        source="acct-0001",
        destination="acct-0000",
        as_of="2026-01-15T09:00:00Z",
        truncated=False,
    )
    assert early["features"]["dst_amount_in_15m"] == 150_000
    with connect(db_path) as connection:
        window, _truncated = load_window(connection, as_of="2026-01-15T09:00:00Z")
    assert [item.transaction_id for item in window] == ["txn-000000"]


def test_cross_bank_fan_out_has_reason_codes_and_no_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "score.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    with _client(db_path) as client:
        fan_out = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "fan-out"},
        )
        hop = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000011", "idempotency_key": "hop"},
        )
    assert fan_out.status_code == 200
    body = fan_out.json()
    assert body["from_bank_id"] != body["to_bank_id"]
    assert {"FAN_OUT", "HIGH_VELOCITY"} <= set(body["reason_codes"])
    assert body["decision"] in {"REVIEW", "HIGH"}
    assert body["score_kind"] == "experimental_score"
    assert body["receipt_status"] == "SIGNED"
    assert body["anchor_status"] == "PENDING"
    assert body["scoring_mode"] == "rule_only"
    assert _FORBIDDEN.isdisjoint(_keys(body))
    hop_body = hop.json()
    assert {"RAPID_ONWARD", "MULTI_HOP"} <= set(hop_body["reason_codes"])
    assert _FORBIDDEN.isdisjoint(_keys(hop_body))


def test_idempotent_replay_and_conflicting_key(tmp_path: Path) -> None:
    first_db = tmp_path / "one.db"
    second_db = tmp_path / "two.db"
    seed_database(first_db, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    seed_database(second_db, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    with _client(first_db) as client:
        original = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "same"},
        )
        replay = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "same"},
        )
        conflict = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000000", "idempotency_key": "same"},
        )
        missing = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-missing", "idempotency_key": "missing"},
        )
        loaded = client.get(f"/api/v1/decisions/{original.json()['decision_id']}")
    assert original.status_code == 200
    assert replay.json()["decision_id"] == original.json()["decision_id"]
    assert replay.json()["feature_snapshot_sha256"] == original.json()["feature_snapshot_sha256"]
    assert replay.json()["risk_score"] == original.json()["risk_score"]
    assert conflict.status_code == 409
    assert missing.status_code == 404
    assert loaded.json()["anchor_status"] == "PENDING"
    assert loaded.json()["receipt_status"] == "SIGNED"
    with connect(first_db) as connection:
        decisions = connection.execute("SELECT COUNT(*) AS total FROM decisions").fetchone()[
            "total"
        ]
        snapshots = connection.execute(
            "SELECT COUNT(*) AS total FROM feature_snapshots"
        ).fetchone()["total"]
        receipts = connection.execute("SELECT COUNT(*) AS total FROM evidence_receipts").fetchone()[
            "total"
        ]
        outbox = connection.execute("SELECT COUNT(*) AS total FROM anchor_outbox").fetchone()[
            "total"
        ]
    assert decisions == 1
    assert snapshots == 1
    assert receipts == 1
    assert outbox == 1
    with _client(second_db) as client:
        other = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "same"},
        )
    assert other.json()["risk_score"] == original.json()["risk_score"]
    assert other.json()["reason_codes"] == original.json()["reason_codes"]
    assert other.json()["feature_snapshot_sha256"] == original.json()["feature_snapshot_sha256"]


def test_score_boundaries_and_formula() -> None:
    assert [decision_band(score) for score in (0, 39, 40, 69, 70, 100)] == [
        "LOW",
        "LOW",
        "REVIEW",
        "REVIEW",
        "HIGH",
        "HIGH",
    ]
    assert combine_scores(0, 100) == (60, "hybrid_experimental")
    assert combine_scores(100, 0) == (40, "hybrid_experimental")
    assert combine_scores(65, None) == (65, "rule_only")


def test_hybrid_model_trains_once_on_a_separate_population(tmp_path: Path) -> None:
    artifact = tmp_path / "iforest.joblib"
    metadata = train_model(artifact, seed=7, rows=80)
    assert metadata["training_seed"] == 7
    assert metadata["model_version"] == "iforest-v1"
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert digest == metadata["artifact_sha256"]
    db_path = tmp_path / "hybrid.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    settings = Settings(
        db_path=db_path,
        scoring_mode="hybrid",
        model_path=artifact,
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "hybrid"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["scoring_mode"] == "hybrid_experimental"
    assert body["model_version"] == "iforest-v1"
    assert body["ml_normalized_score"] is not None
    expected, mode = combine_scores(body["rule_score"], body["ml_normalized_score"])
    assert mode == "hybrid_experimental"
    assert body["risk_score"] == expected
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == digest
    sidecar = json.loads(artifact.with_suffix(".json").read_text(encoding="utf-8"))
    assert sidecar["training_seed"] == 7
    assert "scenario_id" not in sidecar["feature_names"]


def test_subgraph_is_capped(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    with _client(db_path) as client:
        capped = client.get("/api/v1/graph/subgraph?transaction_id=txn-000007&max_nodes=2")
        too_wide = client.get("/api/v1/graph/subgraph?transaction_id=txn-000007&max_nodes=101")
    assert capped.status_code == 200
    assert capped.json()["node_count"] <= 2
    assert "label" not in json.dumps(capped.json())
    assert too_wide.status_code == 422


def test_synthetic_report_states_the_caveat(tmp_path: Path) -> None:
    report = synthetic_report(tmp_path / "report.db")
    assert report["positives"] == 12
    assert 0 <= report["precision"] <= 1
    assert 0 <= report["recall"] <= 1
    assert "not production" in report["caveat"]
    assert report["score_kind"] == "experimental_score"


def test_scoring_modules_do_not_read_ground_truth() -> None:
    root = Path(__file__).resolve().parents[2] / "veritas"
    for relative in (
        "decisions/service.py",
        "graph/features.py",
        "graph/window.py",
        "risk/rules.py",
        "risk/model.py",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "scenario_ground_truth" not in text
        assert "MULE_ACCOUNT" not in text


def test_node_cap_is_reported_when_more_accounts_remain() -> None:
    transfers = [
        Transfer(
            f"txn-{index:06d}",
            f"acct-{index:04d}",
            f"acct-{index + 1:04d}",
            100,
            "2026-01-15T09:00:00Z",
        )
        for index in range(8)
    ]
    graph = bounded_subgraph(
        transfers,
        source="acct-0000",
        destination="acct-0001",
        max_nodes=4,
        max_edges=200,
    )
    assert len(graph["nodes"]) == 4
    assert graph["truncated"] is True


def test_import_does_not_load_sklearn() -> None:
    code = (
        "import resource, sys\n"
        "import veritas.api.app\n"
        "rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "print('sklearn', 'sklearn' in sys.modules)\n"
        "print('rss', rss)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "sklearn False" in completed.stdout
    rss = int(completed.stdout.split("rss", 1)[1].strip())
    assert rss < 800_000_000
