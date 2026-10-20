"""Outage routes RPC away from Anvil. The chain process and its state file stay up."""

import socket
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from veritas.decisions.service import evaluate_transaction
from veritas.evidence.keys import ensure_signing_key
from veritas.ledger.client import LedgerClient, LedgerConfig, RpcRoute
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.workers.anchor import PUBLIC_ANCHOR_ADDRESS
from veritas.workers.outbox import process_once

_ROOT = Path(__file__).resolve().parents[3]
_ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
_RPC = "http://127.0.0.1:8545"
_CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
_NOW = datetime(2026, 10, 20, 6, 30, tzinfo=UTC)


class CountingClient:
    def __init__(self, inner: LedgerClient) -> None:
        self.inner = inner
        self.sends = 0

    def validate(self) -> None:
        self.inner.validate()

    def get_decision(self, key: bytes):
        return self.inner.get_decision(key)

    def send_anchor(self, from_address: str, key: bytes, evidence_digest: bytes) -> str:
        self.sends += 1
        return self.inner.send_anchor(from_address, key, evidence_digest)

    def transaction_receipt(self, tx_hash: str):
        return self.inner.transaction_receipt(tx_hash)


def test_closed_port_outage_recovers_without_resetting_anvil(tmp_path: Path) -> None:
    if _port_open(8545):
        raise AssertionError("port 8545 is already in use")
    state = tmp_path / "anvil-state.json"
    log = tmp_path / "anvil.log"
    handle = log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(_ANVIL),
            "--host",
            "127.0.0.1",
            "--port",
            "8545",
            "--chain-id",
            "31337",
            "--state",
            str(state),
            "--state-interval",
            "60",
        ],
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait(8545)
        deploy = subprocess.run(
            ["sh", str(_ROOT / "contracts/script/deploy-local.sh")],
            check=False,
            cwd=_ROOT,
            capture_output=True,
            text=True,
        )
        if deploy.returncode != 0:
            raise AssertionError("local deploy failed")
        before = _block_number()
        db_path = tmp_path / "route.db"
        seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
        key_path = tmp_path / "issuer.pem"
        ensure_signing_key(key_path, "issuer-local-1")
        decision = evaluate_transaction(
            db_path,
            transaction_id="txn-000011",
            idempotency_key="rpc-route",
            scoring_mode="rule_only",
            signing_key_path=key_path,
            signing_key_id="issuer-local-1",
        )
        assert decision["anchor_status"] == "PENDING"
        route = RpcRoute(_RPC)
        route.unavailable = True
        inner = LedgerClient(
            LedgerConfig(
                rpc_url=_RPC,
                chain_id=31337,
                contract_address=_CONTRACT,
                runtime_code_sha256=PINNED_RUNTIME_SHA256,
            ),
            timeout_seconds=0.4,
            route=route,
        )
        counted = CountingClient(inner)
        with connect(db_path) as connection:
            outage = process_once(connection, counted, from_address=PUBLIC_ANCHOR_ADDRESS, now=_NOW)
            waiting = process_once(
                connection, counted, from_address=PUBLIC_ANCHOR_ADDRESS, now=_NOW
            )
            assert process.poll() is None
            assert _block_number() >= before
            route.unavailable = False
            recovered = None
            for step in range(4):
                recovered = process_once(
                    connection,
                    counted,
                    from_address=PUBLIC_ANCHOR_ADDRESS,
                    now=_NOW + timedelta(seconds=3 + step),
                )
                if recovered is not None and recovered.status == "CONFIRMED":
                    break
            duplicate = process_once(
                connection,
                counted,
                from_address=PUBLIC_ANCHOR_ADDRESS,
                now=_NOW + timedelta(seconds=8),
            )
        assert outage is not None
        assert outage.error_category == "RPC_UNAVAILABLE"
        assert outage.status == "PENDING"
        assert waiting is None
        assert recovered is not None
        assert recovered.status == "CONFIRMED"
        assert duplicate is None
        assert counted.sends == 1
        assert process.poll() is None
        assert _block_number() >= before
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        handle.close()


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _wait(port: int) -> None:
    for _ in range(30):
        if _port_open(port):
            return
        time.sleep(0.2)
    raise AssertionError("anvil did not listen")


def _block_number() -> int:
    import json
    import urllib.request

    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}
    ).encode()
    request = urllib.request.Request(_RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.load(response)
    return int(payload["result"], 16)
