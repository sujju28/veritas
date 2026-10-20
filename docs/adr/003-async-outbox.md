# ADR-003 — Asynchronous anchor outbox

## Status

Accepted.

## Decision

`POST /api/v1/decisions/evaluate` returns after the SQLite transaction commits. The anchor status is `PENDING`. A separate worker claims one outbox row, submits it to Anvil, and confirms the stored digest before marking the job `CONFIRMED`.

## Why

Scoring must not wait on chain confirmation. An RPC outage leaves the decision in place and the job queued. The worker backs off and, when the original RPC returns, confirms the same digest without a second conflicting anchor.

## Consequence

Callers must read `anchor_status` separately from the risk decision. `PENDING` means the receipt is signed and the chain commitment is not confirmed. It is not `VERIFIED_ONCHAIN`.
