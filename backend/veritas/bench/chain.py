"""Time one RPC read and one anchor while a temporary Anvil keeps its own state file."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from veritas.bench.study import _rss_bytes, port_open, summarize
from veritas.decisions.service import evaluate_transaction
from veritas.evidence.keys import ensure_signing_key
from veritas.ledger.client import LedgerClient, LedgerConfig
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.workers.anchor import PUBLIC_ANCHOR_ADDRESS
from veritas.workers.outbox import process_once

_CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
_RPC = "http://127.0.0.1:8545"


def measure_chain(output_dir: Path, *, seed: int, samples: int) -> dict[str, Any]:
    if port_open("127.0.0.1", 8545):
        return {"measured": False, "reason": "127.0.0.1:8545 is already in use", "rows": []}
    anvil = Path.home() / ".foundry" / "bin" / "anvil"
    if not anvil.is_file():
        return {"measured": False, "reason": "anvil is not installed", "rows": []}
    state = output_dir / ".bench-anvil-state.json"
    log_handle = (output_dir / ".bench-anvil.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(anvil),
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
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait()
        root = Path(__file__).resolve().parents[3]
        deploy = subprocess.run(
            ["sh", str(root / "contracts/script/deploy-local.sh")],
            check=False,
            cwd=root,
            capture_output=True,
            text=True,
        )
        if deploy.returncode != 0:
            return {"measured": False, "reason": "local deploy failed", "rows": []}
        client = LedgerClient(
            LedgerConfig(
                rpc_url=_RPC,
                chain_id=31337,
                contract_address=_CONTRACT,
                runtime_code_sha256=PINNED_RUNTIME_SHA256,
            )
        )
        empty = bytes.fromhex("11" * 32)
        reads = []
        for _ in range(samples):
            started = time.perf_counter()
            client.get_decision(empty)
            reads.append((time.perf_counter() - started) * 1000)
        anchor_ms = _time_anchor(output_dir, client, seed)
        return {
            "measured": True,
            "reason": "temporary Anvil state file, stopped after the sample",
            "rows": [
                {
                    "scale": "chain",
                    "seed": seed,
                    "accounts": 0,
                    "transactions": 0,
                    "rss_bytes": _rss_bytes(),
                    "operation": "rpc_read",
                    **summarize(reads),
                },
                {
                    "scale": "chain",
                    "seed": seed,
                    "accounts": 100,
                    "transactions": 500,
                    "rss_bytes": _rss_bytes(),
                    "operation": "anchor_confirm",
                    **summarize([anchor_ms]),
                },
            ],
        }
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log_handle.close()
        state.unlink(missing_ok=True)


def _time_anchor(output_dir: Path, client: LedgerClient, seed: int) -> float:
    database = output_dir / ".bench-anchor.db"
    seed_database(database, seed=seed, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = output_dir / ".bench-issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    evaluate_transaction(
        database,
        transaction_id="txn-000011",
        idempotency_key="bench-anchor",
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    started = time.perf_counter()
    with connect(database) as connection:
        for _ in range(6):
            outcome = process_once(connection, client, from_address=PUBLIC_ANCHOR_ADDRESS)
            if outcome is not None and outcome.status == "CONFIRMED":
                _remove_db(database)
                return (time.perf_counter() - started) * 1000
    _remove_db(database)
    raise RuntimeError("anchor confirmation did not finish")


def _remove_db(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(str(path) + "-wal").unlink(missing_ok=True)
    Path(str(path) + "-shm").unlink(missing_ok=True)


def _wait() -> None:
    for _ in range(30):
        if port_open("127.0.0.1", 8545):
            return
        time.sleep(0.2)
    raise RuntimeError("anvil did not listen")
