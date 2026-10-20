# HTTP API

The API is a FastAPI application on `127.0.0.1:8000`, one Uvicorn worker, base path `/api/v1`. The machine-readable contract is [`openapi.json`](openapi.json) (OpenAPI 3.1.0, title `VERITAS`, version `0.1.0`). It is generated from the application code, not written by hand.

Regenerate and check it from the repository root:

```bash
cd backend && ../.venv/bin/python -c \
  "import json; from veritas.api.app import app; print(json.dumps(app.openapi(), indent=2))" \
  > ../docs/openapi.json
```

At Phase 09 the generated document equalled the committed file.

## Endpoints

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /health` | Liveness | Does not touch the chain |
| `GET /ready` | Local dependency check | Reports a warning when no chain is configured |
| `POST /scenarios/generate` | Seed synthetic data | `tiny`, `default`, or `benchmark` scale. Benchmark needs explicit confirmation |
| `GET /scenarios` | List planted scenarios | Ground-truth labels are not exposed |
| `GET /transactions?limit=&offset=` | Page through transactions | Page size is capped at 100 |
| `GET /graph/subgraph?transaction_id=&max_nodes=` | Bounded neighbourhood | Hard limit 100 nodes. `truncated` is set when it is reached |
| `POST /decisions/evaluate` | Score a transaction | Body is `transaction_id` and `idempotency_key`. Returns the decision, reason codes, and `anchor_status`. Replaying the key returns the stored decision |
| `GET /decisions/{decision_id}` | Read a decision | |
| `GET /decisions/{decision_id}/receipt` | Export the signed receipt | Schema `EvidenceReceipt`, protocol 1.0 |
| `GET /decisions/{decision_id}/anchor` | Anchor status, tx hash, block | `PENDING` until the worker confirms |
| `POST /verify` | Check a receipt copy | Dashboard helper. It does not score or store the copy and is not the independent verifier |

The authoritative independent check is the CLI `python -m veritas.verifier verify`, which does not call this API. See [`PROTOCOL.md`](PROTOCOL.md).

## Errors

Errors use one JSON shape and omit stack traces and local paths:

```json
{"error": {"code": "NOT_FOUND", "message": "...", "correlation_id": "...", "details": []}}
```

Codes include `BAD_REQUEST` (400), `NOT_FOUND` (404), `METHOD_NOT_ALLOWED` (405), `VALIDATION_ERROR` (422), and `INTERNAL_ERROR` (500). `details` appears on validation errors.

## Semantics callers must keep separate

- `decision` and `risk_score` are an **experimental score** from `rules-v1`, optionally combined with an anomaly experiment. It is not a probability of fraud.
- `anchor_status` is independent of the decision. `PENDING` means the receipt is signed and the chain commitment is not yet confirmed.
- Decision responses never include ground-truth labels.

## Security notes

The server refuses non-loopback bind hosts and a non-loopback chain RPC URL. CORS allows one origin, `http://127.0.0.1:5173` by default (`VERITAS_CORS_ORIGIN`). There are no key-management or admin endpoints. There is no authentication, because the service is local-only and must not be exposed to a network.
