"""RPC outage leaves the decision pending, then one recovery anchor is enough."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from veritas.api.app import create_app
from veritas.api.settings import Settings
from veritas.bench.study import percentile
from veritas.evidence.keys import ensure_signing_key
from veritas.ledger.client import (
    ChainRpcError,
    LedgerClient,
    LedgerConfig,
    OnChainDecision,
    RpcRoute,
)
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.workers.outbox import process_once

_FROM = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
_NOW = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)


class FaultChain:
    def __init__(self) -> None:
        self.down = True
        self.sends = 0
        self.digest: bytes | None = None

    def validate(self) -> None:
        if self.down:
            raise ChainRpcError("injected RPC outage")

    def get_decision(self, key: bytes) -> OnChainDecision:
        del key
        self.validate()
        if self.digest is None:
            return OnChainDecision(False, bytes(32), "0x" + "00" * 20, 0, 0)
        return OnChainDecision(True, self.digest, _FROM.lower(), 4, 10)

    def send_anchor(self, from_address: str, key: bytes, evidence_digest: bytes) -> str:
        del from_address, key
        self.validate()
        self.sends += 1
        self.digest = evidence_digest
        return "0x" + "ab" * 32

    def transaction_receipt(self, tx_hash: str) -> dict[str, object] | None:
        del tx_hash
        self.validate()
        return {"status": "0x1", "blockNumber": "0x4"}


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([10, 30, 20], 50) == 20
    assert percentile([10, 30, 20], 99) == 30


def test_closed_port_is_an_rpc_failure() -> None:
    route = RpcRoute("http://127.0.0.1:8545", unavailable=True)
    client = LedgerClient(
        LedgerConfig(
            rpc_url=route.primary_url,
            chain_id=31337,
            contract_address="0x5FbDB2315678afecb367f032d93F642f64180aa3",
            runtime_code_sha256=PINNED_RUNTIME_SHA256,
        ),
        timeout_seconds=0.4,
        route=route,
    )
    try:
        client.validate()
    except ChainRpcError:
        return
    raise AssertionError("a closed loopback port was treated as a live chain")


def test_decision_stays_pending_and_recovery_anchors_once(tmp_path: Path) -> None:
    db_path = tmp_path / "outage.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = tmp_path / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    settings = Settings(
        db_path=db_path,
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
        contract_address="",
    )
    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/v1/decisions/evaluate",
            json={"transaction_id": "txn-000007", "idempotency_key": "outage"},
        )
    body = created.json()
    assert created.status_code == 200
    assert body["anchor_status"] == "PENDING"
    assert body["decision_id"].startswith("dec-")
    chain = FaultChain()
    with connect(db_path) as connection:
        first = process_once(connection, chain, from_address=_FROM, now=_NOW)
        during_backoff = process_once(connection, chain, from_address=_FROM, now=_NOW)
        chain.down = False
        recovered = process_once(
            connection,
            chain,
            from_address=_FROM,
            now=_NOW + timedelta(seconds=3),
        )
        again = process_once(
            connection,
            chain,
            from_address=_FROM,
            now=_NOW + timedelta(seconds=4),
        )
        stored = connection.execute(
            "SELECT anchor_status FROM decisions WHERE decision_id = ?",
            (body["decision_id"],),
        ).fetchone()
    assert first is not None
    assert first.status == "PENDING"
    assert first.error_category == "RPC_UNAVAILABLE"
    assert during_backoff is None
    assert recovered is not None
    assert recovered.status == "CONFIRMED"
    assert again is None
    assert chain.sends == 1
    assert stored["anchor_status"] == "CONFIRMED"
