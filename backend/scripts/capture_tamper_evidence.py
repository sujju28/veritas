"""Capture a live-chain tamper transcript for the publication folder.

Starts a temporary Anvil on 127.0.0.1:8545 with its state in a temporary directory,
deploys the registries, scores one seeded transaction in a temporary database, anchors it,
then runs the independent verifier CLI on the original receipt, a tampered copy, a re-signed
copy with a mismatched ruleset, a wrong contract address, and the original receipt again after
Anvil is stopped.

Port 8545 must be free. Nothing outside the temporary directory is changed except the
gitignored `.env.local` that `contracts/script/deploy-local.sh` writes.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from veritas.decisions.service import evaluate_transaction, get_receipt
from veritas.evidence.keys import ensure_signing_key, load_private_key, registry_path_for
from veritas.evidence.models import EvidencePayload
from veritas.evidence.sign import sign_payload
from veritas.ledger.client import LedgerClient, LedgerConfig
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.simulator.store import seed_database
from veritas.storage.db import connect
from veritas.workers.anchor import PUBLIC_ANCHOR_ADDRESS
from veritas.workers.outbox import process_once

ROOT = Path(__file__).resolve().parents[2]
ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
RPC = "http://127.0.0.1:8545"
CHAIN_ID = 31337
CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
WRONG_CONTRACT = "0x000000000000000000000000000000000000dEaD"
TRANSACTION_ID = "txn-000007"
IDEMPOTENCY_KEY = "phase09-live-tamper"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if _port_open():
        print("port 8545 is already in use", file=sys.stderr)
        return 2
    lines: list[str] = []
    with tempfile.TemporaryDirectory(prefix="veritas-tamper-", dir=ROOT / "data") as raw:
        work = Path(raw)
        log_handle = (work / "anvil.log").open("w", encoding="utf-8")
        process = subprocess.Popen(
            [
                str(ANVIL),
                "--host",
                "127.0.0.1",
                "--port",
                "8545",
                "--chain-id",
                str(CHAIN_ID),
                "--state",
                str(work / "anvil-state.json"),
                "--state-interval",
                "60",
            ],
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_port()
            _run_all(work, process, lines)
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            log_handle.close()
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


def _run_all(work: Path, process: subprocess.Popen[bytes], lines: list[str]) -> None:
    deploy = subprocess.run(
        ["sh", str(ROOT / "contracts/script/deploy-local.sh")],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    deploy_line = deploy.stdout.strip().splitlines()[-1]
    env_lines = (ROOT / ".env.local").read_text().splitlines()
    ruleset_addr = next(
        (
            line.split("=")[1].strip()
            for line in env_lines
            if line.startswith("VERITAS_RULESET_REGISTRY_ADDRESS=")
        ),
        None,
    )

    db_path = work / "live.db"
    seed_database(db_path, seed=42, scale="tiny", replace=False, confirm_benchmark=False)
    key_path = work / "issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    decision = evaluate_transaction(
        db_path,
        transaction_id=TRANSACTION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        scoring_mode="rule_only",
        signing_key_path=key_path,
        signing_key_id="issuer-local-1",
    )
    receipt = get_receipt(db_path, decision["decision_id"])
    assert receipt is not None
    client = LedgerClient(
        LedgerConfig(
            rpc_url=RPC,
            chain_id=CHAIN_ID,
            contract_address=CONTRACT,
            runtime_code_sha256=PINNED_RUNTIME_SHA256,
        )
    )
    outcome = None
    with connect(db_path) as connection:
        for _ in range(4):
            outcome = process_once(connection, client, from_address=PUBLIC_ANCHOR_ADDRESS)
            if outcome is not None and outcome.status == "CONFIRMED":
                break
    assert outcome is not None and outcome.status == "CONFIRMED", "anchor was not confirmed"

    original = work / "receipt.json"
    original.write_text(json.dumps(receipt), encoding="utf-8")

    tampered_receipt = json.loads(original.read_text(encoding="utf-8"))
    original_score = tampered_receipt["payload"]["risk_score"]
    tampered_receipt["payload"]["risk_score"] = 1
    tampered = work / "receipt-tampered.json"
    tampered.write_text(json.dumps(tampered_receipt), encoding="utf-8")

    # Re-signed with mismatched ruleset_sha256
    mismatched_payload = EvidencePayload(
        **{
            **receipt["payload"],
            "ruleset_sha256": "00" * 32,
        }
    )
    mismatched_receipt_obj, _ = sign_payload(
        mismatched_payload,
        load_private_key(key_path),
        "issuer-local-1",
    )
    mismatched = work / "receipt-mismatched-ruleset.json"
    mismatched.write_text(json.dumps(mismatched_receipt_obj.model_dump()), encoding="utf-8")

    trusted = registry_path_for(key_path)

    lines += [
        f"# Live-chain tamper capture, {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"# Host {platform.platform()} {platform.machine()}, Python {platform.python_version()}",
        "# Anvil is one temporary local process. Its state was in a temporary directory.",
        f"# {deploy_line}",
        f"# Seed 42 tiny, {TRANSACTION_ID}, idempotency key {IDEMPOTENCY_KEY}.",
        f"# Decision {decision['decision_id']}, score {original_score}.",
        f"# Anchor outcome {outcome.status}, tx {outcome.tx_hash}, block {outcome.block_number}.",
        f"# Stored digest {receipt['digest_hex']}.",
        "# The tampered copy changes payload.risk_score from "
        f"{original_score} to 1. Exit 0 means VERIFIED_ONCHAIN only.",
        "# The mismatched ruleset copy is validly signed but claims ruleset_sha256 00...00.",
        "# This shows integrity of the receipt, not that the decision was correct.",
        "",
    ]
    lines += _cli("1. original receipt, chain running", original, trusted, CONTRACT, ruleset_addr)
    lines += _cli(
        "2. tampered copy (unsigned edit), chain running",
        tampered,
        trusted,
        CONTRACT,
        ruleset_addr,
    )
    lines += _cli(
        "3. re-signed with mismatched ruleset_sha256, chain running",
        mismatched,
        trusted,
        CONTRACT,
        ruleset_addr,
    )
    lines += _cli(
        "4. original receipt, wrong contract address",
        original,
        trusted,
        WRONG_CONTRACT,
        ruleset_addr,
    )
    process.terminate()
    process.wait(timeout=10)
    lines += _cli("5. original receipt, Anvil stopped", original, trusted, CONTRACT, ruleset_addr)


def _cli(
    label: str,
    receipt: Path,
    trusted: Path,
    contract: str,
    ruleset_addr: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "veritas.verifier",
        "verify",
        "--receipt",
        str(receipt),
        "--trusted-keys",
        str(trusted),
        "--rpc-url",
        RPC,
        "--chain-id",
        str(CHAIN_ID),
        "--contract-address",
        contract,
        "--json",
    ]
    shown = (
        f"$ python -m veritas.verifier verify --receipt {receipt.name} --trusted-keys "
        f"trust-registry.json --rpc-url {RPC} --chain-id {CHAIN_ID} --contract-address {contract}"
    )
    if ruleset_addr:
        command += ["--ruleset-address", ruleset_addr]
        shown += f" --ruleset-address {ruleset_addr}"
    shown += " --json"
    done = subprocess.run(
        command, cwd=ROOT / "backend", capture_output=True, text=True, check=False
    )
    output = done.stdout.strip() or done.stderr.strip()
    return [f"## {label}", shown, output, f"exit {done.returncode}", ""]


def _port_open() -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", 8545)) == 0


def _wait_for_port() -> None:
    for _ in range(50):
        if _port_open():
            return
        time.sleep(0.2)
    raise RuntimeError("anvil did not listen on 127.0.0.1:8545")


if __name__ == "__main__":
    raise SystemExit(main())
