"""Persist one experimental decision and its feature snapshot."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veritas.evidence.keys import load_private_key
from veritas.evidence.models import EvidencePayload
from veritas.evidence.sign import sign_payload
from veritas.graph.features import feature_snapshot
from veritas.graph.window import Transfer, load_window
from veritas.risk.model import MODEL_VERSION, load_model, normalized_anomaly
from veritas.risk.rules import RULESET_VERSION, apply_rules, combine_scores, decision_band
from veritas.storage.db import apply_migrations, connect, transaction

ANCHOR_STATUS = "PENDING"
RECEIPT_STATUS = "SIGNED"

_PUBLIC_KEYS = (
    "decision_id",
    "transaction_id",
    "idempotency_key",
    "risk_score",
    "decision",
    "score_kind",
    "scoring_mode",
    "reason_codes",
    "ruleset_version",
    "model_version",
    "rule_score",
    "ml_normalized_score",
    "feature_snapshot_sha256",
    "from_bank_id",
    "to_bank_id",
    "triggered_rules",
    "features",
    "receipt_status",
    "anchor_status",
    "created_at",
)


class UnknownTransaction(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


def evaluate_transaction(
    db_path: Path,
    *,
    transaction_id: str,
    idempotency_key: str,
    scoring_mode: str = "auto",
    model_path: Path | None = None,
    signing_key_path: Path,
    signing_key_id: str,
) -> dict[str, Any]:
    with connect(db_path) as connection:
        apply_migrations(connection)
        with transaction(connection):
            existing = _by_key(connection, idempotency_key)
            if existing is not None:
                if existing["transaction_id"] != transaction_id:
                    raise IdempotencyConflict("idempotency key is already bound")
                return _public(existing)
            subject = _subject(connection, transaction_id)
            if subject is None:
                raise UnknownTransaction("transaction was not found")
            stored = _insert_decision(
                connection,
                subject=subject,
                idempotency_key=idempotency_key,
                scoring_mode=scoring_mode,
                model_path=model_path,
                signing_key_path=signing_key_path,
                signing_key_id=signing_key_id,
            )
            return _public(stored)


def get_receipt(db_path: Path, decision_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        apply_migrations(connection)
        row = connection.execute(
            "SELECT * FROM evidence_receipts WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        payload = EvidencePayload.model_validate_json(row["canonical_text"])
        return {
            "payload": payload.model_dump(),
            "digest_hex": row["digest_hex"],
            "signature_b64": row["signature_b64"],
            "signing_key_id": row["signing_key_id"],
            "signature_algorithm": row["signature_algorithm"],
        }


def get_anchor(db_path: Path, decision_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        apply_migrations(connection)
        row = connection.execute(
            """
            SELECT d.decision_id, d.anchor_status, o.status AS outbox_status,
                   o.error_category, o.submitted_tx_hash, o.block_number
            FROM decisions AS d
            LEFT JOIN anchor_outbox AS o ON o.decision_id = d.decision_id
            WHERE d.decision_id = ?
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "decision_id": row["decision_id"],
            "anchor_status": row["anchor_status"],
            "outbox_status": row["outbox_status"],
            "error_category": row["error_category"],
            "tx_hash": row["submitted_tx_hash"],
            "block_number": row["block_number"],
        }


def get_decision(db_path: Path, decision_id: str) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        apply_migrations(connection)
        row = connection.execute(
            "SELECT * FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return _public(_hydrate(connection, row))


def _insert_decision(
    connection: sqlite3.Connection,
    *,
    subject: dict[str, Any],
    idempotency_key: str,
    scoring_mode: str,
    model_path: Path | None,
    signing_key_path: Path,
    signing_key_id: str,
) -> dict[str, Any]:
    private_key = load_private_key(signing_key_path)
    transfers, truncated = load_window(connection, as_of=subject["event_time"])
    transfers = _with_subject(transfers, subject)
    snapshot = feature_snapshot(
        transfers,
        transaction_id=subject["transaction_id"],
        source=subject["from_account_id"],
        destination=subject["to_account_id"],
        as_of=subject["event_time"],
        truncated=truncated,
    )
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    rule_score, triggered = apply_rules(snapshot["features"])
    ml_score, model_version, mode = _ml_component(
        snapshot["features"],
        scoring_mode=scoring_mode,
        model_path=model_path,
    )
    risk_score, mode = combine_scores(rule_score, ml_score if mode != "rule_only" else None)
    if mode == "rule_only":
        ml_score = None
        model_version = "rule-only"
    material = f"{idempotency_key}\n{subject['transaction_id']}".encode()
    decision_id = "dec-" + hashlib.sha256(material).hexdigest()[:20]
    snapshot_id = "snap-" + decision_id.removeprefix("dec-")
    created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    reason_codes = sorted({item["code"] for item in triggered})
    explanation = {
        "score_kind": "experimental_score",
        "note": "Experimental score, not a calibrated probability.",
        "triggered_rules": triggered,
        "features": snapshot["features"],
        "from_bank_id": subject["from_bank_id"],
        "to_bank_id": subject["to_bank_id"],
    }
    connection.execute(
        """
        INSERT INTO feature_snapshots (
            snapshot_id, transaction_id, schema_version, payload_json, digest_hex
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (snapshot_id, subject["transaction_id"], snapshot["schema_version"], canonical, digest),
    )
    connection.execute(
        """
        INSERT INTO decisions (
            decision_id, idempotency_key, transaction_id, risk_score, decision_category,
            reason_codes, model_version, ruleset_version, created_at, scoring_mode, score_kind,
            rule_score, ml_normalized_score, explanation_json, feature_snapshot_id,
            anchor_status, receipt_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            idempotency_key,
            subject["transaction_id"],
            risk_score,
            decision_band(risk_score),
            json.dumps(reason_codes, separators=(",", ":")),
            model_version,
            RULESET_VERSION,
            created_at,
            mode,
            "experimental_score",
            rule_score,
            ml_score,
            json.dumps(explanation, sort_keys=True, separators=(",", ":"), allow_nan=False),
            snapshot_id,
            ANCHOR_STATUS,
            RECEIPT_STATUS,
        ),
    )
    payload = EvidencePayload(
        schema_version="1.0",
        decision_id=decision_id,
        transaction_id=subject["transaction_id"],
        bank_id=subject["from_bank_id"],
        decision=decision_band(risk_score),
        risk_score=risk_score,
        reason_codes=reason_codes,
        feature_snapshot_sha256=digest,
        model_version=model_version,
        ruleset_version=RULESET_VERSION,
        decision_timestamp=created_at,
    )
    receipt, canonical_text = sign_payload(payload, private_key, signing_key_id)
    connection.execute(
        """
        INSERT INTO evidence_receipts (
            decision_id, canonical_text, digest_hex, signature_b64,
            signing_key_id, signature_algorithm, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            canonical_text,
            receipt.digest_hex,
            receipt.signature_b64,
            receipt.signing_key_id,
            receipt.signature_algorithm,
            created_at,
        ),
    )
    connection.execute(
        """
        INSERT INTO anchor_outbox (
            job_id, decision_id, status, attempts, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "job-" + decision_id.removeprefix("dec-"),
            decision_id,
            ANCHOR_STATUS,
            0,
            created_at,
            created_at,
        ),
    )
    return {
        "decision_id": decision_id,
        "transaction_id": subject["transaction_id"],
        "idempotency_key": idempotency_key,
        "risk_score": risk_score,
        "decision": decision_band(risk_score),
        "score_kind": "experimental_score",
        "scoring_mode": mode,
        "reason_codes": reason_codes,
        "ruleset_version": RULESET_VERSION,
        "model_version": model_version,
        "rule_score": rule_score,
        "ml_normalized_score": ml_score,
        "feature_snapshot_sha256": digest,
        "from_bank_id": subject["from_bank_id"],
        "to_bank_id": subject["to_bank_id"],
        "triggered_rules": triggered,
        "features": snapshot["features"],
        "receipt_status": RECEIPT_STATUS,
        "anchor_status": ANCHOR_STATUS,
        "created_at": created_at,
    }


def _ml_component(
    features: dict[str, Any],
    *,
    scoring_mode: str,
    model_path: Path | None,
) -> tuple[int | None, str, str]:
    if scoring_mode == "rule_only":
        return None, "rule-only", "rule_only"
    loaded, reason = load_model(model_path)
    if loaded is None:
        del reason
        return None, "rule-only", "rule_only"
    score = normalized_anomaly(loaded, features)
    if score is None:
        return None, "rule-only", "rule_only"
    return score, MODEL_VERSION, "hybrid_experimental"


def _subject(connection: sqlite3.Connection, transaction_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT t.transaction_id, t.from_account_id, t.to_account_id, t.amount_minor,
               t.event_time, src.bank_id AS from_bank_id, dst.bank_id AS to_bank_id
        FROM transactions AS t
        JOIN accounts AS src ON src.account_id = t.from_account_id
        JOIN accounts AS dst ON dst.account_id = t.to_account_id
        WHERE t.transaction_id = ?
        """,
        (transaction_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _by_key(connection: sqlite3.Connection, idempotency_key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM decisions WHERE idempotency_key = ?",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    return _hydrate(connection, row)


def _hydrate(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    explanation = json.loads(row["explanation_json"])
    snapshot = connection.execute(
        "SELECT digest_hex FROM feature_snapshots WHERE snapshot_id = ?",
        (row["feature_snapshot_id"],),
    ).fetchone()
    return {
        "decision_id": row["decision_id"],
        "transaction_id": row["transaction_id"],
        "idempotency_key": row["idempotency_key"],
        "risk_score": int(row["risk_score"]),
        "decision": row["decision_category"],
        "score_kind": row["score_kind"],
        "scoring_mode": row["scoring_mode"],
        "reason_codes": json.loads(row["reason_codes"]),
        "ruleset_version": row["ruleset_version"],
        "model_version": row["model_version"],
        "rule_score": int(row["rule_score"]),
        "ml_normalized_score": row["ml_normalized_score"],
        "feature_snapshot_sha256": None if snapshot is None else snapshot["digest_hex"],
        "from_bank_id": explanation.get("from_bank_id"),
        "to_bank_id": explanation.get("to_bank_id"),
        "triggered_rules": explanation.get("triggered_rules", []),
        "features": explanation.get("features", {}),
        "receipt_status": row["receipt_status"],
        "anchor_status": row["anchor_status"],
        "created_at": row["created_at"],
    }


def _with_subject(transfers: list[Transfer], subject: dict[str, Any]) -> list[Transfer]:
    if any(item.transaction_id == subject["transaction_id"] for item in transfers):
        return transfers
    covered = list(transfers)
    covered.append(
        Transfer(
            transaction_id=subject["transaction_id"],
            from_account_id=subject["from_account_id"],
            to_account_id=subject["to_account_id"],
            amount_minor=int(subject["amount_minor"]),
            event_time=subject["event_time"],
        )
    )
    covered.sort(key=lambda item: (item.event_time, item.transaction_id))
    return covered


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in _PUBLIC_KEYS}
