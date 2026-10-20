# Local runbook

Development machine: Apple Silicon, 8 GB unified memory, native macOS processes. Do not start the API, Anvil, the dashboard, and a benchmark at the same time.

## Startup order

1. `make setup` once, from the repository root.
2. `make seed` when `data/veritas.db` is missing. Seed 42, default scale: 300 accounts and 2,000 transactions.
3. `make backend` in its own terminal. It listens on `127.0.0.1:8000` with one worker.
4. `make frontend` in its own terminal. It listens on `127.0.0.1:5173`.
5. Optional chain: `make chain-start`, then `make contract-deploy`, then `make worker`.

## Demo commands

```bash
curl -sS http://127.0.0.1:8000/api/v1/health
curl -sS -X POST http://127.0.0.1:8000/api/v1/decisions/evaluate \
  -H 'Content-Type: application/json' \
  -d '{"transaction_id":"txn-000007","idempotency_key":"demo-fan-out"}'
```

`txn-000007` is the seeded cross-bank fan-out. The dashboard can score it from the Transactions or Decision card. The receipt card edits a browser copy only.

## Screenshots

Open `http://127.0.0.1:5173` after the API is healthy. Capture the overview, the decision for `txn-000007`, the receipt tamper result, and a graph that shows the 100-node warning. Save those images only after the page has rendered live data. The images from the Phase 09 capture are under `docs/publication/images/`.

## Stop and cleanup

Stop the frontend, the worker, the API, and Anvil with Ctrl-C in each terminal. Confirm the ports are free:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:8545 -sTCP:LISTEN
```

Deleting `data/veritas.db` removes the synthetic dataset. Deleting `.anvil/` removes local commitments. Deleting `.local/keys/` removes the issuer key. None of those paths are committed. Do not delete directories that this project did not create.

## Outage

Point the worker at `http://127.0.0.1:9`, or set `RpcRoute.unavailable`, while Anvil keeps running. The decision stays `PENDING`. Restore the original RPC URL and let the worker confirm the same digest once.

## Benchmark

`make benchmark` is the explicit 10,000-transaction run. It needs port 8545 free because it starts a temporary Anvil. Results land in `docs/benchmarks/`.
