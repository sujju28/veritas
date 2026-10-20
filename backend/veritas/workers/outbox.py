"""Claim and settle one outbox job. RPC calls stay outside the SQLite transaction."""

from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from veritas.ledger.client import (
    ChainConfigError,
    ChainResetError,
    ChainRpcError,
    ContractRejected,
    OnChainDecision,
)
from veritas.ledger.commitment import decision_key
from veritas.storage.db import transaction

MAX_ATTEMPTS = 8
LEASE_SECONDS = 30


class AnchorChain(Protocol):
    def validate(self) -> None: ...

    def get_decision(self, key: bytes) -> OnChainDecision: ...

    def send_anchor(self, from_address: str, key: bytes, evidence_digest: bytes) -> str: ...

    def transaction_receipt(self, tx_hash: str) -> dict[str, object] | None: ...


@dataclass(frozen=True)
class JobOutcome:
    job_id: str
    decision_id: str
    status: str
    error_category: str | None
    tx_hash: str | None
    block_number: int | None


def retry_delay_seconds(attempt: int, rng: random.Random) -> float:
    base = min(60.0, float(2 ** max(attempt - 1, 0)))
    return base + rng.uniform(0, base * 0.25)


def process_once(
    connection: sqlite3.Connection,
    chain: AnchorChain,
    *,
    from_address: str,
    now: datetime | None = None,
    rng: random.Random | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> JobOutcome | None:
    clock = now or datetime.now(UTC)
    generator = rng or random.Random()
    job = _claim(connection, clock)
    if job is None:
        return None
    outcome = _advance(job, chain, from_address=from_address)
    if outcome.status in {"PENDING", "SUBMITTED"} and int(job["attempts"]) >= max_attempts:
        outcome = JobOutcome(
            job_id=outcome.job_id,
            decision_id=outcome.decision_id,
            status="FAILED",
            error_category=outcome.error_category or "MAX_RETRY",
            tx_hash=outcome.tx_hash,
            block_number=outcome.block_number,
        )
    delay = retry_delay_seconds(int(job["attempts"]), generator)
    _settle(connection, outcome, clock=clock, delay_seconds=delay)
    return outcome


def _advance(job: sqlite3.Row, chain: AnchorChain, *, from_address: str) -> JobOutcome:
    key = decision_key(job["decision_id"])
    digest = bytes.fromhex(job["digest_hex"])
    tx_hash = job["submitted_tx_hash"]
    try:
        chain.validate()
        current = chain.get_decision(key)
    except ChainResetError:
        return _pending(job, "CHAIN_RESET", tx_hash)
    except ChainConfigError:
        return _failed(job, "CONFIG_MISMATCH", tx_hash)
    except ChainRpcError:
        return _pending(job, "RPC_UNAVAILABLE", tx_hash)
    if current.exists:
        return _from_commitment(job, current, tx_hash)
    if tx_hash:
        return _from_receipt(job, chain, key, digest, tx_hash)
    try:
        submitted = chain.send_anchor(from_address, key, digest)
    except ContractRejected:
        return _after_revert(job, chain, key, digest, tx_hash)
    except ChainRpcError:
        return _pending(job, "RPC_UNAVAILABLE", None)
    return _from_receipt(job, chain, key, digest, submitted)


def _from_receipt(
    job: sqlite3.Row,
    chain: AnchorChain,
    key: bytes,
    digest: bytes,
    tx_hash: str,
) -> JobOutcome:
    try:
        receipt = _await_receipt(chain, tx_hash)
    except ChainRpcError:
        return _submitted(job, "RPC_UNAVAILABLE", tx_hash)
    if receipt is None:
        return _submitted(job, "STILL_PENDING", tx_hash)
    status = receipt.get("status")
    if status in {"0x1", "0x01", 1}:
        try:
            current = chain.get_decision(key)
        except ChainRpcError:
            return _submitted(job, "RPC_UNAVAILABLE", tx_hash)
        if current.exists:
            return _from_commitment(job, current, tx_hash, receipt)
        return _submitted(job, "STILL_PENDING", tx_hash)
    return _after_revert(job, chain, key, digest, tx_hash)


def _after_revert(
    job: sqlite3.Row,
    chain: AnchorChain,
    key: bytes,
    digest: bytes,
    tx_hash: str | None,
) -> JobOutcome:
    try:
        current = chain.get_decision(key)
    except ChainRpcError:
        return _pending(job, "RPC_UNAVAILABLE", tx_hash)
    if current.exists and current.evidence_digest == digest:
        return _confirmed(job, tx_hash, current.block_number)
    if current.exists:
        return _failed(job, "DIGEST_CONFLICT", tx_hash)
    return _failed(job, "CONTRACT_REJECTED", tx_hash)


def _from_commitment(
    job: sqlite3.Row,
    current: OnChainDecision,
    tx_hash: str | None,
    receipt: dict[str, object] | None = None,
) -> JobOutcome:
    digest = bytes.fromhex(job["digest_hex"])
    if current.evidence_digest != digest:
        return _failed(job, "DIGEST_CONFLICT", tx_hash)
    block = current.block_number
    if receipt is not None and receipt.get("blockNumber") is not None:
        block = int(str(receipt["blockNumber"]), 16)
    return _confirmed(job, tx_hash, block)


def _await_receipt(chain: AnchorChain, tx_hash: str) -> dict[str, object] | None:
    """Poll a few times so a just-mined local block is visible before the next retry."""
    receipt = None
    for attempt in range(8):
        receipt = chain.transaction_receipt(tx_hash)
        if receipt is not None:
            return receipt
        if attempt < 7:
            time.sleep(0.05)
    return receipt


def _claim(connection: sqlite3.Connection, now: datetime) -> sqlite3.Row | None:
    stamp = _format(now)
    lease = _format(now - timedelta(seconds=LEASE_SECONDS))
    with transaction(connection):
        connection.execute(
            """
            UPDATE anchor_outbox
            SET status = CASE WHEN submitted_tx_hash IS NULL THEN 'PENDING' ELSE 'SUBMITTED' END,
                updated_at = ?
            WHERE status = 'IN_PROGRESS' AND updated_at < ?
            """,
            (stamp, lease),
        )
        row = connection.execute(
            """
            SELECT o.job_id, o.decision_id, o.status, o.attempts, o.submitted_tx_hash,
                   r.digest_hex
            FROM anchor_outbox AS o
            JOIN evidence_receipts AS r ON r.decision_id = o.decision_id
            WHERE o.status IN ('PENDING', 'SUBMITTED')
              AND (o.next_retry_at IS NULL OR o.next_retry_at <= ?)
            ORDER BY o.created_at
            LIMIT 1
            """,
            (stamp,),
        ).fetchone()
        if row is None:
            return None
        cursor = connection.execute(
            """
            UPDATE anchor_outbox
            SET status = 'IN_PROGRESS', attempts = attempts + 1, updated_at = ?,
                error_category = NULL
            WHERE job_id = ? AND status IN ('PENDING', 'SUBMITTED')
            """,
            (stamp, row["job_id"]),
        )
        if cursor.rowcount != 1:
            return None
        claimed = connection.execute(
            """
            SELECT o.job_id, o.decision_id, o.status, o.attempts, o.submitted_tx_hash,
                   r.digest_hex
            FROM anchor_outbox AS o
            JOIN evidence_receipts AS r ON r.decision_id = o.decision_id
            WHERE o.job_id = ?
            """,
            (row["job_id"],),
        ).fetchone()
    return claimed


def _settle(
    connection: sqlite3.Connection,
    outcome: JobOutcome,
    *,
    clock: datetime,
    delay_seconds: float,
) -> None:
    stamp = _format(clock)
    retry_at = None
    anchor_status = "PENDING"
    if outcome.status in {"PENDING", "SUBMITTED"}:
        retry_at = _format(clock + timedelta(seconds=delay_seconds))
    elif outcome.status == "CONFIRMED":
        anchor_status = "CONFIRMED"
    elif outcome.error_category == "DIGEST_CONFLICT":
        anchor_status = "CONFLICT"
    elif outcome.error_category == "CONTRACT_REJECTED":
        anchor_status = "REJECTED"
    with transaction(connection):
        connection.execute(
            """
            UPDATE anchor_outbox
            SET status = ?, error_category = ?, submitted_tx_hash = ?, block_number = ?,
                next_retry_at = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (
                outcome.status,
                outcome.error_category,
                outcome.tx_hash,
                outcome.block_number,
                retry_at,
                stamp,
                outcome.job_id,
            ),
        )
        connection.execute(
            "UPDATE decisions SET anchor_status = ? WHERE decision_id = ?",
            (anchor_status, outcome.decision_id),
        )


def _pending(job: sqlite3.Row, category: str, tx_hash: str | None) -> JobOutcome:
    status = "SUBMITTED" if tx_hash else "PENDING"
    return JobOutcome(job["job_id"], job["decision_id"], status, category, tx_hash, None)


def _submitted(job: sqlite3.Row, category: str, tx_hash: str) -> JobOutcome:
    return JobOutcome(job["job_id"], job["decision_id"], "SUBMITTED", category, tx_hash, None)


def _failed(job: sqlite3.Row, category: str, tx_hash: str | None) -> JobOutcome:
    return JobOutcome(job["job_id"], job["decision_id"], "FAILED", category, tx_hash, None)


def _confirmed(job: sqlite3.Row, tx_hash: str | None, block_number: int) -> JobOutcome:
    return JobOutcome(
        job["job_id"],
        job["decision_id"],
        "CONFIRMED",
        None,
        tx_hash,
        block_number,
    )


def _format(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
