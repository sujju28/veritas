# Release notes draft

Draft only. Do not publish, tag, or push until the maintainer approves it.

## veritas 0.1.0

Local synthetic fraud-decision prototype for an Apple Silicon Mac with 8 GB of memory. Research and demonstration only.

### What is in it

- Three logical simulated banks, seed 42, default 300 accounts and 2,000 transactions. Dataset fingerprint `cd1955ac9585643c7f67a7e12abc65dcfd905f135db7e21ef1f1d41680dc5ca0`.
- Rule scoring (`rules-v1`) with reason codes, a signed RFC 8785 / SHA-256 / Ed25519 receipt (protocol 1.0), and a SQLite outbox.
- `DecisionRegistry` on one native Anvil process, chain id 31337. Runtime bytecode SHA-256 `9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db`.
- Independent verifier CLI (`python -m veritas.verifier`) and a Vite dashboard on `127.0.0.1:5173`.
- Raw measurements in `docs/benchmarks/` from 2026-10-20T06:25:13Z.
- A live-chain verifier transcript, `docs/publication/tamper-cli-live.txt`: `VERIFIED_ONCHAIN` for the original receipt, `TAMPERED` for a copy with a changed score, `CONFIG_MISMATCH` for a wrong contract address, and `VERIFICATION_UNAVAILABLE` with Anvil stopped. Regenerate with `make capture-tamper`.
- Documents: architecture (Mermaid), threat model, runbook, API and OpenAPI, protocol and verifier statuses, three ADRs, third-party licenses, secret-scan guide.

### Limits you should read before using it

- This release is **not** a four-validator Besu network, has **no** institutionally independent nodes, and is **not** a bank consortium. Anvil can be reset by whoever runs it.
- The dataset and its labels are synthetic and were produced by this project's own generator. No real banking, customer, or employer data is included.
- This is not a production fraud model. On the tiny seed-42 set the rule-only report records precision 0.0084 and recall 0.25 (353 of 356 flagged transfers were legitimate).
- Anchor confirmation timing is a single sample. Percentiles elsewhere use 15 samples after 2 warm-ups on one machine.
- A holder of the issuer key can re-sign altered content. The receipt check shows integrity, not decision correctness.

### Continuous integration

GitHub Actions runs Python unit tests with Ruff, frontend tests and build, and Foundry tests, on x86_64 Linux. Dependencies come from `backend/requirements.lock` and `frontend/package-lock.json`, and third-party actions are pinned to commit SHAs. The workflow has not yet run on GitHub. Integration against local Anvil (`make test-e2e`, `make capture-tamper`) is reproduced separately on a machine with Foundry 1.8.5 and is not part of CI.

### License

MIT. Third-party notices: `docs/publication/THIRD_PARTY.md`. A transitive build-tool dependency (`lightningcss`, MPL-2.0) is noted there. It is not included in the repository.

### Known follow-ups

- Clean-checkout reproduction in a temporary directory (awaiting approval).
- First GitHub Actions run.
- Dashboard capture of an anchored receipt and of the fraud-ring graph (not yet captured).
