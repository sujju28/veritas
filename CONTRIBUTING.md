# Contributing

This prototype targets an Apple Silicon Mac with 8 GB of unified memory. Changes should keep the native-process layout: one Uvicorn worker, SQLite, optional Anvil, and the Vite dashboard. Do not add Besu, PostgreSQL, Redis, Kafka, Neo4j, Docker, or a remote inference service.

## Local checks

```bash
make setup
make test-unit
make lint
make format-check
make contract-test
(cd frontend && npm ci)
make frontend-test
make frontend-build
```

`make test-e2e`, `make capture-tamper`, and `make benchmark` start a temporary Anvil on `127.0.0.1:8545`. Run them only when that port is free, and do not run them together with the dashboard. GitHub Actions runs the unit, frontend, and Foundry jobs. It does not start Anvil. The live anchor path stays a local reproduction.

## Data and keys

Use seed 42 and the scales in `backend/veritas/simulator/scales.py`. Do not commit a database, a private key, `.env.local`, or Anvil state. Do not add real customer, account, or institution data.

## License

Contributions are under the MIT license in `LICENSE`. Dependency licenses are recorded in `docs/publication/THIRD_PARTY.md`.
