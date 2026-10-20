"""Outbox retries and the independent verifier. Neither path calls the scoring API."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from veritas.decisions.service import evaluate_transaction, get_receipt
from veritas.evidence.keys import ensure_signing_key, load_trust_registry, registry_path_for
from veritas.ledger.client import (
    ChainConfigError,
    ChainResetError,
    ChainRpcError,
    ContractRejected,
    OnChainDecision,
)
from veritas.ledger.commitment import decision_key
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.verifier.check import verify_on_chain
from veritas.workers.outbox import process_once

_FROM = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
_NOW = datetime(2026, 10, 19, 15, 0, tzinfo=UTC)


class FakeChain:
    def __init__(self) -> None:
        self.rows: dict[bytes, bytes] = {}
        self.receipts: dict[str, dict[str, object] | None] = {}
        self.sent: list[bytes] = []
        self.mode = "ok"

    def validate(self) -> None:
        if self.mode == "rpc":
            raise ChainRpcError("down")
        if self.mode == "config":
            raise ChainConfigError("chain id does not match")
        if self.mode == "reset":
            raise ChainResetError("configured contract has no code")

    def get_decision(self, key: bytes) -> OnChainDecision:
        self.validate()
        digest = self.rows.get(key)
        if digest is None:
            return OnChainDecision(False, bytes(32), "0x" + "00" * 20, 0, 0)
        return OnChainDecision(True, digest, _FROM.lower(), 4, 10)

    def send_anchor(self, from_address: str, key: bytes, evidence_digest: bytes) -> str:
        del from_address
        self.validate()
        if self.mode == "reject":
            raise ContractRejected("reverted")
        self.sent.append(key)
        self.rows[key] = evidence_digest
        tx_hash = "0x" + "ab" * 32
        self.receipts[tx_hash] = {"status": "0x1", "blockNumber": "0x4"}
        return tx_hash

    def transaction_receipt(self, tx_hash: str) -> dict[str, object] | None:
        self.validate()
        return self.receipts.get(tx_hash)


def _ready(tmp_path: Path) -> tuple[Path, str, bytes]:
    db_path = tmp_path / "decisions.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    body = evaluate_transaction(
        db_path,
        transaction_id="txn-000007",
        idempotency_key="anchor-once",
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    evaluate_transaction(
        db_path,
        transaction_id="txn-000007",
        idempotency_key="anchor-once",
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    return db_path, body["decision_id"], decision_key(body["decision_id"])


def _digest(db_path: Path, decision_id: str) -> bytes:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT digest_hex FROM evidence_receipts WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
    return bytes.fromhex(row["digest_hex"])


def test_duplicate_outbox_and_confirm_without_a_second_submit(tmp_path: Path) -> None:
    db_path, decision_id, key = _ready(tmp_path)
    with connect(db_path) as connection:
        jobs = connection.execute("SELECT COUNT(*) AS total FROM anchor_outbox").fetchone()["total"]
    assert jobs == 1
    chain = FakeChain()
    chain.rows[key] = _digest(db_path, decision_id)
    with connect(db_path) as connection:
        outcome = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert outcome is not None
    assert outcome.status == "CONFIRMED"
    assert chain.sent == []
    with connect(db_path) as connection:
        anchor = connection.execute(
            "SELECT anchor_status FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()["anchor_status"]
    assert anchor == "CONFIRMED"


def test_restart_confirms_a_submitted_job_and_conflict_stops(tmp_path: Path) -> None:
    db_path, decision_id, key = _ready(tmp_path)
    digest = _digest(db_path, decision_id)
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE anchor_outbox
            SET status = 'SUBMITTED', submitted_tx_hash = '0xabc',
                updated_at = '2026-10-19T14:00:00Z'
            WHERE decision_id = ?
            """,
            (decision_id,),
        )
        connection.commit()
    chain = FakeChain()
    chain.rows[key] = digest
    with connect(db_path) as connection:
        outcome = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert outcome is not None
    assert outcome.status == "CONFIRMED"
    assert chain.sent == []
    chain.rows[key] = b"\x03" * 32
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE anchor_outbox
            SET status = 'PENDING', next_retry_at = NULL
            WHERE decision_id = ?
            """,
            (decision_id,),
        )
        connection.commit()
        conflict = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert conflict is not None
    assert conflict.status == "FAILED"
    assert conflict.error_category == "DIGEST_CONFLICT"


def test_rpc_outage_is_not_confirmation_and_waits(tmp_path: Path) -> None:
    db_path, decision_id, _key = _ready(tmp_path)
    chain = FakeChain()
    chain.mode = "rpc"
    with connect(db_path) as connection:
        outcome = process_once(connection, chain, from_address=_FROM, now=_NOW)
        again = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert outcome is not None
    assert outcome.status == "PENDING"
    assert outcome.error_category == "RPC_UNAVAILABLE"
    assert again is None
    with connect(db_path) as connection:
        anchor = connection.execute(
            "SELECT anchor_status FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()["anchor_status"]
    assert anchor == "PENDING"


def test_chain_reset_and_contract_rejection(tmp_path: Path) -> None:
    db_path, _decision_id, _key = _ready(tmp_path)
    chain = FakeChain()
    chain.mode = "reset"
    with connect(db_path) as connection:
        reset = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert reset is not None
    assert reset.error_category == "CHAIN_RESET"
    assert reset.status == "PENDING"
    chain.mode = "reject"
    with connect(db_path) as connection:
        connection.execute("UPDATE anchor_outbox SET status = 'PENDING', next_retry_at = NULL")
        connection.commit()
        rejected = process_once(connection, chain, from_address=_FROM, now=_NOW)
    assert rejected is not None
    assert rejected.status == "FAILED"
    assert rejected.error_category == "CONTRACT_REJECTED"


def test_two_workers_claim_one_job(tmp_path: Path) -> None:
    db_path, decision_id, _key = _ready(tmp_path)
    chain = FakeChain()
    outcomes: list[object] = []
    lock = threading.Lock()

    def _run() -> None:
        with connect(db_path) as connection:
            outcome = process_once(connection, chain, from_address=_FROM, now=_NOW)
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    confirmed = [item for item in outcomes if item is not None]
    assert len(confirmed) == 1
    assert confirmed[0].status == "CONFIRMED"
    assert len(chain.sent) == 1
    with connect(db_path) as connection:
        jobs = connection.execute(
            "SELECT COUNT(*) AS total FROM anchor_outbox WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()["total"]
    assert jobs == 1


def test_verifier_statuses(tmp_path: Path) -> None:
    db_path, decision_id, key = _ready(tmp_path)
    key_path = tmp_path / "issuer.pem"
    registry = load_trust_registry(registry_path_for(key_path)).model_dump()
    receipt = get_receipt(db_path, decision_id)
    assert receipt is not None
    chain = FakeChain()
    chain.rows[key] = _digest(db_path, decision_id)
    verified = _with_fake(receipt, registry, chain)
    assert verified["status"] == "VERIFIED_ONCHAIN"
    changed = json.loads(json.dumps(receipt))
    changed["payload"]["risk_score"] = 1
    assert (
        verify_on_chain(
            changed,
            registry,
            rpc_url="http://127.0.0.1:9",
            chain_id=31337,
            contract_address="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )["status"]
        == "TAMPERED"
    )
    assert (
        verify_on_chain(
            receipt,
            {"keys": []},
            rpc_url="http://127.0.0.1:9",
            chain_id=31337,
            contract_address="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )["status"]
        == "UNKNOWN_ISSUER"
    )
    chain.rows.clear()
    assert _with_fake(receipt, registry, chain)["status"] == "PENDING_ANCHOR"
    chain.rows[key] = b"\x04" * 32
    assert _with_fake(receipt, registry, chain)["status"] == "ONCHAIN_MISMATCH"
    chain.mode = "config"
    assert _with_fake(receipt, registry, chain)["status"] == "CONFIG_MISMATCH"
    chain.mode = "rpc"
    outage = _with_fake(receipt, registry, chain)
    assert outage["status"] == "VERIFICATION_UNAVAILABLE"
    assert outage["status"] != "VERIFIED_ONCHAIN"
    text = Path(__file__).resolve().parents[2].joinpath("veritas/verifier/check.py").read_text()
    assert "veritas.api" not in text
    assert "veritas.decisions" not in text
    assert "/verify" not in text


def _with_fake(receipt: dict[str, object], registry: dict[str, object], chain: FakeChain) -> dict:
    from veritas.verifier import check

    original = check.LedgerClient

    class _Client:
        def __init__(self, config: object) -> None:
            del config

        def validate(self) -> None:
            chain.validate()

        def get_decision(self, key: bytes) -> OnChainDecision:
            return chain.get_decision(key)

    check.LedgerClient = _Client
    try:
        return check.verify_on_chain(
            receipt,
            registry,
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337,
            contract_address="0x5FbDB2315678afecb367f032d93F642f64180aa3",
        )
    finally:
        check.LedgerClient = original
