"""Time local scoring and evidence steps. Chain timings are omitted when RPC is down."""

from __future__ import annotations

import csv
import json
import math
import platform
import resource
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veritas.evidence.canonical import canonical_bytes
from veritas.evidence.keys import (
    ensure_signing_key,
    load_private_key,
    load_trust_registry,
    registry_path_for,
)
from veritas.evidence.models import EvidencePayload
from veritas.evidence.sign import sign_payload
from veritas.evidence.verify import verify_offline
from veritas.graph.features import feature_snapshot
from veritas.graph.window import load_window
from veritas.risk.rules import apply_rules
from veritas.simulator.store import seed_database
from veritas.storage.db import connect

_SCALES = ("tiny", "default", "benchmark")


def percentile(samples: list[float], percent: float) -> float:
    """Nearest-rank percentile. The input is a list of milliseconds."""
    if not samples:
        raise ValueError("percentile needs at least one sample")
    ordered = sorted(samples)
    rank = math.ceil(percent / 100 * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def summarize(samples: list[float]) -> dict[str, float | int]:
    return {
        "n": len(samples),
        "p50_ms": percentile(samples, 50),
        "p95_ms": percentile(samples, 95),
        "p99_ms": percentile(samples, 99),
    }


def run_study(
    output_dir: Path,
    *,
    seed: int = 42,
    warmup: int = 2,
    samples: int = 15,
    scales: tuple[str, ...] = _SCALES,
) -> dict[str, Any]:
    if warmup < 1 or samples < 1:
        raise ValueError("warmup and samples must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = _payload()
    key_path = output_dir / ".bench-issuer.pem"
    ensure_signing_key(key_path, "issuer-local-1")
    private_key = load_private_key(key_path)
    registry = load_trust_registry(registry_path_for(key_path)).model_dump()
    rows: list[dict[str, Any]] = []
    for scale in scales:
        database = output_dir / f".bench-{scale}.db"
        if database.exists():
            database.unlink()
        started = time.perf_counter()
        seeded = seed_database(
            database,
            seed=seed,
            scale=scale,
            replace=False,
            confirm_benchmark=scale == "benchmark",
        )
        generation_ms = (time.perf_counter() - started) * 1000
        subject = _subject(database)
        score_samples = _repeat(
            warmup,
            samples,
            lambda database=database, subject=subject: _score(database, subject),
        )
        canonical_samples = _repeat(
            warmup,
            samples,
            lambda payload=payload: canonical_bytes(payload.model_dump()),
        )
        sign_samples = _repeat(
            warmup,
            samples,
            lambda payload=payload, private_key=private_key: sign_payload(
                payload, private_key, "issuer-local-1"
            ),
        )
        signed, _canonical = sign_payload(payload, private_key, "issuer-local-1")
        verify_samples = _repeat(
            warmup,
            samples,
            lambda signed=signed, registry=registry: verify_offline(signed.model_dump(), registry),
        )
        common = {
            "scale": scale,
            "seed": seed,
            "accounts": seeded["accounts"],
            "transactions": seeded["transactions"],
            "rss_bytes": _rss_bytes(),
        }
        rows.append({**common, "operation": "dataset_generate", **summarize([generation_ms])})
        rows.append({**common, "operation": "graph_score", **summarize(score_samples)})
        rows.append({**common, "operation": "canonical", **summarize(canonical_samples)})
        rows.append({**common, "operation": "sign", **summarize(sign_samples)})
        rows.append({**common, "operation": "offline_verify", **summarize(verify_samples)})
        _remove_sqlite(database)
    document = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "git_revision": _git_revision(),
        "os": platform.platform(),
        "machine": platform.machine(),
        "ram_bytes": _physical_ram(),
        "python": sys.version.split()[0],
        "warmup": warmup,
        "samples": samples,
        "scoring_mode": "rule_only",
        "percentile_method": "nearest-rank",
        "units": {"latency": "milliseconds", "rss": "bytes", "ram": "bytes"},
        "rows": rows,
        "chain": {"measured": False, "reason": "chain timings are recorded by the chain section"},
    }
    return document


def write_study(output_dir: Path, document: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "study.json").write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    fieldnames = [
        "scale",
        "operation",
        "n",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "accounts",
        "transactions",
        "rss_bytes",
        "seed",
        "generated_at",
        "git_revision",
        "os",
        "machine",
        "ram_bytes",
        "python",
        "latency_unit",
        "rss_unit",
    ]
    with (output_dir / "study.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in document["rows"]:
            writer.writerow(
                {
                    **row,
                    "generated_at": document["generated_at"],
                    "git_revision": document["git_revision"],
                    "os": document["os"],
                    "machine": document["machine"],
                    "ram_bytes": document["ram_bytes"],
                    "python": document["python"],
                    "latency_unit": "milliseconds",
                    "rss_unit": "bytes",
                }
            )


def port_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _repeat(warmup: int, samples: int, operation: Any) -> list[float]:
    for _ in range(warmup):
        operation()
    measured: list[float] = []
    for _ in range(samples):
        started = time.perf_counter()
        operation()
        measured.append((time.perf_counter() - started) * 1000)
    return measured


def _score(database: Path, subject: dict[str, str]) -> None:
    with connect(database) as connection:
        transfers, truncated = load_window(connection, as_of=subject["event_time"])
    snapshot = feature_snapshot(
        transfers,
        transaction_id=subject["transaction_id"],
        source=subject["from_account_id"],
        destination=subject["to_account_id"],
        as_of=subject["event_time"],
        truncated=truncated,
    )
    apply_rules(snapshot["features"])


def _subject(database: Path) -> dict[str, str]:
    with connect(database) as connection:
        row = connection.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, event_time
            FROM transactions
            ORDER BY event_time DESC, transaction_id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        raise RuntimeError("seeded database has no transactions")
    return {key: str(row[key]) for key in row.keys()}


def _payload() -> EvidencePayload:
    return EvidencePayload(
        schema_version="1.0",
        decision_id="dec-bench",
        transaction_id="txn-bench",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=0,
        reason_codes=[],
        feature_snapshot_sha256="ab" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        decision_timestamp="2026-01-15T09:00:00Z",
    )


def _remove_sqlite(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(str(path) + "-wal").unlink(missing_ok=True)
    Path(str(path) + "-shm").unlink(missing_ok=True)


def _rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(usage)
    return int(usage) * 1024


def _physical_ram() -> int:
    completed = subprocess.run(
        ["sysctl", "-n", "hw.memsize"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return 0
    return int(completed.stdout.strip() or "0")


def _git_revision() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "none"
    return completed.stdout.strip() or "none"
