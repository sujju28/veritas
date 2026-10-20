"""Experimental risk decisions and their signed off-chain receipts."""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from veritas.api.errors import ApiError
from veritas.api.settings import Settings
from veritas.decisions.requests import ScoringRequest
from veritas.decisions.service import (
    IdempotencyConflict,
    UnknownTransaction,
    evaluate_transaction,
    get_anchor,
    get_decision,
    get_receipt,
)
from veritas.evidence.keys import SigningKeyError, ensure_signing_key
from veritas.evidence.models import EvidenceReceipt
from veritas.graph.features import bounded_subgraph
from veritas.graph.window import load_window
from veritas.storage.db import apply_migrations, connect

router = APIRouter(prefix="/api/v1")
_MAX_NODES = Query(50, ge=1, le=100)


class DecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    transaction_id: str
    idempotency_key: str
    risk_score: int = Field(ge=0, le=100)
    decision: str
    score_kind: str
    scoring_mode: str
    reason_codes: list[str]
    ruleset_version: str
    model_version: str
    rule_score: int
    ml_normalized_score: int | None
    feature_snapshot_sha256: str | None
    from_bank_id: str | None
    to_bank_id: str | None
    triggered_rules: list[dict[str, object]]
    features: dict[str, object]
    receipt_status: str
    anchor_status: str
    created_at: str


@router.post("/decisions/evaluate", response_model=DecisionResponse)
def evaluate(body: ScoringRequest, request: Request) -> DecisionResponse:
    settings: Settings = request.app.state.settings
    try:
        ensure_signing_key(settings.signing_key_path, settings.signing_key_id)
        payload = evaluate_transaction(
            settings.db_path,
            transaction_id=body.transaction_id,
            idempotency_key=body.idempotency_key,
            scoring_mode=settings.scoring_mode,
            model_path=settings.model_path,
            signing_key_path=settings.signing_key_path,
            signing_key_id=settings.signing_key_id,
        )
    except UnknownTransaction as exc:
        raise ApiError("TRANSACTION_NOT_FOUND", str(exc), 404) from exc
    except IdempotencyConflict as exc:
        raise ApiError("IDEMPOTENCY_CONFLICT", str(exc), 409) from exc
    except SigningKeyError as exc:
        raise ApiError("SIGNING_KEY_UNAVAILABLE", str(exc), 503) from exc
    return DecisionResponse.model_validate(payload)


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
def read_decision(decision_id: str, request: Request) -> DecisionResponse:
    settings: Settings = request.app.state.settings
    payload = get_decision(settings.db_path, decision_id)
    if payload is None:
        raise ApiError("DECISION_NOT_FOUND", "decision was not found", 404)
    return DecisionResponse.model_validate(payload)


@router.get("/decisions/{decision_id}/receipt", response_model=EvidenceReceipt)
def read_receipt(decision_id: str, request: Request) -> EvidenceReceipt:
    settings: Settings = request.app.state.settings
    payload = get_receipt(settings.db_path, decision_id)
    if payload is None:
        raise ApiError("RECEIPT_NOT_FOUND", "receipt was not found", 404)
    return EvidenceReceipt.model_validate(payload)


@router.get("/decisions/{decision_id}/anchor")
def read_anchor(decision_id: str, request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    payload = get_anchor(settings.db_path, decision_id)
    if payload is None:
        raise ApiError("DECISION_NOT_FOUND", "decision was not found", 404)
    return payload


@router.get("/graph/subgraph")
def subgraph(
    request: Request,
    transaction_id: str,
    max_nodes: int = _MAX_NODES,
) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    with connect(settings.db_path) as connection:
        apply_migrations(connection)
        row = connection.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, event_time
            FROM transactions
            WHERE transaction_id = ?
            """,
            (transaction_id,),
        ).fetchone()
        if row is None:
            raise ApiError("TRANSACTION_NOT_FOUND", "transaction was not found", 404)
        transfers, truncated = load_window(connection, as_of=row["event_time"])
    graph = bounded_subgraph(
        transfers,
        source=row["from_account_id"],
        destination=row["to_account_id"],
        max_nodes=max_nodes,
        max_edges=200,
    )
    return {
        "transaction_id": transaction_id,
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "truncated": bool(graph["truncated"] or truncated),
        "nodes": graph["nodes"],
        "edges": graph["edges"],
    }
