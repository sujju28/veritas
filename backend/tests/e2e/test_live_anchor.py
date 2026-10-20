"""Live Anvil round trip. The verifier does not call the scoring API."""

import json
import socket
import subprocess
import time
from pathlib import Path

from veritas.decisions.service import evaluate_transaction, get_receipt
from veritas.evidence.keys import ensure_signing_key, load_trust_registry, registry_path_for
from veritas.ledger.client import LedgerClient, LedgerConfig
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.verifier.check import verify_on_chain
from veritas.workers.anchor import PUBLIC_ANCHOR_ADDRESS
from veritas.workers.outbox import process_once

_ROOT = Path(__file__).resolve().parents[3]
_ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
_RPC = "http://127.0.0.1:8545"
_CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"


def test_fresh_receipt_anchors_and_outage_is_not_success(tmp_path: Path) -> None:
    if _port_open():
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
        _wait_for_chain()
        deploy = subprocess.run(
            ["sh", str(_ROOT / "contracts/script/deploy-local.sh")],
            check=False,
            cwd=_ROOT,
            capture_output=True,
            text=True,
        )
        (tmp_path / "deploy.log").write_text(deploy.stdout + "\n" + deploy.stderr, encoding="utf-8")
        if deploy.returncode != 0:
            raise AssertionError("local deploy failed")
        db_path = tmp_path / "live.db"
        seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
        key_path = tmp_path / "issuer.pem"
        ensure_signing_key(key_path, "issuer-local-1")
        decision = evaluate_transaction(
            db_path,
            transaction_id="txn-000011",
            idempotency_key="live-anchor",
            scoring_mode="rule_only",
            signing_key_path=key_path,
            signing_key_id="issuer-local-1",
        )
        receipt = get_receipt(db_path, decision["decision_id"])
        assert receipt is not None
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        registry = load_trust_registry(registry_path_for(key_path)).model_dump()
        client = LedgerClient(
            LedgerConfig(
                rpc_url=_RPC,
                chain_id=31337,
                contract_address=_CONTRACT,
                runtime_code_sha256=PINNED_RUNTIME_SHA256,
            )
        )
        outcome = None
        with connect(db_path) as connection:
            for _ in range(4):
                outcome = process_once(connection, client, from_address=PUBLIC_ANCHOR_ADDRESS)
                if outcome is not None and outcome.status == "CONFIRMED":
                    break
        assert outcome is not None
        assert outcome.status == "CONFIRMED"
        verified = verify_on_chain(
            receipt,
            registry,
            rpc_url=_RPC,
            chain_id=31337,
            contract_address=_CONTRACT,
        )
        assert verified["status"] == "VERIFIED_ONCHAIN"
        copied = json.loads(receipt_path.read_text(encoding="utf-8"))
        copied["payload"]["reason_codes"] = ["TAMPER"]
        tampered = verify_on_chain(
            copied,
            registry,
            rpc_url=_RPC,
            chain_id=31337,
            contract_address=_CONTRACT,
        )
        assert tampered["status"] == "TAMPERED"
        process.terminate()
        process.wait(timeout=10)
        process = None
        outage = verify_on_chain(
            receipt,
            registry,
            rpc_url=_RPC,
            chain_id=31337,
            contract_address=_CONTRACT,
        )
        assert outage["status"] == "VERIFICATION_UNAVAILABLE"
        assert "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80" not in json.dumps(
            verified
        )
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        handle.close()


def _port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", 8545)) == 0


def _wait_for_chain() -> None:
    for _ in range(30):
        if _port_open():
            return
        time.sleep(0.2)
    raise AssertionError("anvil did not listen on 127.0.0.1:8545")
