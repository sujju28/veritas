"""Benchmark on-chain replay and ingestion at default scale.

Runs 3 or more iterations of replay and ingest against a local Anvil instance,
records latency statistics, memory (RSS), and environment metadata.
Output is written to docs/benchmarks/onchain_benchmark.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veritas.ledger.client import LedgerConfig
from veritas.onchain.client import (
    PINNED_TRANSFER_LOG_RUNTIME_SHA256,
    TransferLogClient,
)
from veritas.onchain.ingest import ingest_events
from veritas.onchain.replay import replay_dataset
from veritas.simulator.store import seed_database

ROOT = Path(__file__).resolve().parents[2]
ANVIL = Path.home() / ".foundry" / "bin" / "anvil"
RPC = "http://127.0.0.1:8545"
CHAIN_ID = 31337
WRITER_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex(("127.0.0.1", 8545)) == 0


def _max_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return usage
    return usage * 1024


def run_benchmark(output_path: Path, runs: int = 3, scale: str = "default") -> dict[str, Any]:
    if _port_open():
        raise RuntimeError("Port 8545 is already in use. Stop running Anvil before benchmarking.")

    with tempfile.TemporaryDirectory(prefix="veritas-bench-", dir=ROOT / "data") as raw:
        work = Path(raw)
        anvil_log = (work / "anvil.log").open("w", encoding="utf-8")
        anvil_proc = subprocess.Popen(
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
                "1",
            ],
            stdout=anvil_log,
            stderr=subprocess.STDOUT,
        )

        try:
            for _ in range(50):
                if _port_open():
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("Temporary Anvil did not become ready on port 8545")

            # Deploy contracts
            deploy_script = ROOT / "contracts" / "script" / "deploy-local.sh"
            env = dict(os.environ)
            env["RPC_URL"] = RPC
            env["CHAIN_ID"] = str(CHAIN_ID)
            res = subprocess.run(
                [str(deploy_script)], cwd=ROOT, capture_output=True, text=True, env=env
            )
            if res.returncode != 0:
                raise RuntimeError(f"Deploy failed:\n{res.stderr}\n{res.stdout}")

            # Read deployed TransferLog address from .env.local
            env_local = (ROOT / ".env.local").read_text()
            transfer_address = ""
            for line in env_local.splitlines():
                if line.startswith("VERITAS_TRANSFER_LOG_ADDRESS="):
                    transfer_address = line.split("=", 1)[1].strip()
                    break
            if not transfer_address:
                raise RuntimeError("Could not find VERITAS_TRANSFER_LOG_ADDRESS in .env.local")

            client = TransferLogClient(
                LedgerConfig(
                    rpc_url=RPC,
                    chain_id=CHAIN_ID,
                    contract_address=transfer_address,
                    runtime_code_sha256=PINNED_TRANSFER_LOG_RUNTIME_SHA256,
                )
            )

            # Seed source DB
            source_db = work / "source.db"
            seed_info = seed_database(
                source_db, seed=42, scale=scale, replace=False, confirm_benchmark=True
            )
            account_count = seed_info["accounts"]
            transfer_count = seed_info["transactions"]

            replay_times: list[float] = []
            ingest_times: list[float] = []

            for iteration in range(runs):
                target_db = work / f"target_{iteration}.db"

                # Time replay
                t0 = time.perf_counter()
                replay_dataset(source_db, client, WRITER_ADDRESS, batch_size=100)
                t_replay = time.perf_counter() - t0
                replay_times.append(t_replay)

                # Time ingest
                t1 = time.perf_counter()
                ingest_events(target_db, client)
                t_ingest = time.perf_counter() - t1
                ingest_times.append(t_ingest)

            def _stats(samples: list[float]) -> dict[str, float]:
                s = sorted(samples)
                n = len(s)
                return {
                    "runs": n,
                    "min_sec": round(s[0], 4),
                    "max_sec": round(s[-1], 4),
                    "mean_sec": round(sum(s) / n, 4),
                    "p50_sec": round(s[n // 2], 4),
                    "p95_sec": round(s[int(n * 0.95)], 4),
                }

            record = {
                "benchmark": "onchain_replay_and_ingest",
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "scale": scale,
                "accounts": account_count,
                "transfers": transfer_count,
                "runs": runs,
                "replay": _stats(replay_times),
                "ingest": _stats(ingest_times),
                "rss_bytes": _max_rss_bytes(),
                "machine": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "python_version": platform.python_version(),
                },
            }

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(record, indent=2) + "\n")
            return record

        finally:
            anvil_proc.terminate()
            anvil_proc.wait(timeout=5)
            anvil_log.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs" / "benchmarks" / "onchain_benchmark.json",
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--scale", default="default")
    args = parser.parse_args()

    record = run_benchmark(args.output, runs=args.runs, scale=args.scale)
    json.dump(record, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
