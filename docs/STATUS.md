# Project VERITAS — Cursor Delivery Status

**Overall status:** PHASE 09 PREPARED, NOT ACCEPTED. Waiting for explicit approval (clean-checkout check, then GitHub publish). Nothing has been committed, pushed, tagged, or published.  
**Hardware:** MacBook Pro M1 / 8 GB (confirmed: `arm64`, `hw.memsize` 8589934592)  
**Current phase:** 09 — publication/release  
**Last verified commit:** none (Git repository initialized; no commit created)  
**Next step:** maintainer decision on the items in the Phase 09 handoff below

| Phase | State | Tests executed | Notes / blockers |
|---|---|---|---|
| 00 — machine preflight | ACCEPTED | Host inspection plus toolchain version checks. ENV-01 recorded. | Python 3.14.2 venv, Node v24.22.0, Foundry 1.8.5 anvil/forge/cast, all Mach-O arm64. Podman absent. See `docs/ENVIRONMENT.md`. |
| 01 — repository and API | ACCEPTED | `make test-unit`: 9 passed. `make lint` and `make format-check`: passed. Live `GET /api/v1/health` on 127.0.0.1:8000 returned 200. | SQLite stdlib driver. Chain and frontend not started. |
| 02 — data simulator/storage | ACCEPTED | `make test-unit`: 17 passed. `make lint` and `make format-check`: passed. `make seed` wrote 3 banks, 300 accounts, 2,000 transactions. | Ground truth is stored apart from transaction reads. Benchmark requires `CONFIRM=1`. |
| 03 — graph/risk | ACCEPTED | `make test-unit`: 26 passed in 3.08s. `make lint` and `make format-check`: passed. Rule-only report on seed-42 tiny printed precision 0.0084 and recall 0.25. | Cross-bank `txn-000007` is HIGH 100 with `FAN_OUT`, `HIGH_VELOCITY`, `RAPID_ONWARD`. Receipt and anchor stay `NOT_IMPLEMENTED`. |
| 04 — evidence/signatures | ACCEPTED | `make test-unit`: 36 passed in 5.40s. `make lint` and `make format-check`: passed. Offline verifier returned `SIGNATURE_VALID_OFFLINE` for an unmodified receipt and `TAMPERED` for a changed score. | Private key path `.local/keys/` is gitignored. Anchor status stays `PENDING`. |
| 05 — Anvil/contract | ACCEPTED | `make contract-test`: 9 passed. `make test-unit`: 40 passed in 6.29s. `make contract-deploy` on Anvil 1.8.5 at 127.0.0.1:8545 chain id 31337 stored a commitment and rejected a different digest and an unauthorized writer. | Runtime bytecode 1273 bytes, sha256 `9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db`. Anvil was stopped afterward. |
| 06 — outbox/verifier | ACCEPTED | `make test-unit`: 46 passed in 37.13s. `make test-e2e`: 1 passed in 2.70s. `make lint` and `make format-check`: passed. Live path returned `VERIFIED_ONCHAIN`; a changed reason list returned `TAMPERED`; Anvil stopped returned `VERIFICATION_UNAVAILABLE`. | One outbox row per decision. Worker uses the unlocked Anvil account and does not return a private key. |
| 07 — dashboard | ACCEPTED | `make test-unit`: 48 passed in 7.14s. `make frontend-test`: 4 passed. `make frontend-build` succeeded. `make lint` and `make format-check` passed. Browser demo on 127.0.0.1:5173 scored `txn-000007` HIGH 100 and rejected a receipt copy as signature mismatch. | API and Vite were stopped afterward. Anvil was not started. |
| 08 — resilience/benchmarks | ACCEPTED | `make test-unit`: 51 passed in 6.90s. `make test-e2e`: 2 passed in 3.82s. `make lint` and `make format-check` passed. `make benchmark` wrote `docs/benchmarks/` for seed 42, including 1,000 accounts and 10,000 transactions. | RPC outage used a closed loopback port while Anvil stayed up. Peak RSS in the study was 81,543,168 bytes. |
| 09 — publication/release | PREPARED, NOT ACCEPTED | `make test-unit`: 51 passed. `make test-e2e`: 2 passed. `make contract-test`: 9 passed. `make frontend-test`: 4 passed. `make frontend-build`, `make lint`, `make format-check` passed. `make capture-tamper` wrote `docs/publication/tamper-cli-live.txt`. Secret scan on a 148-file publish set was clean. | `docs/ACCEPTANCE.md`: 32 PASS, 0 FAIL, 2 NOT EXECUTED (UI-02 anchored state in a browser, PUB-01 clean checkout). GitHub Actions has not run. Nothing is published. |

## Decision log

- ADR-001: Native macOS first; Podman optional; 8 GB constraints.
- ADR-002: Single local Anvil EVM instead of four-node Besu; no consensus claims.
- ADR-003: SQLite WAL, bounded graphs and one FastAPI worker.
- ADR-004: Canonical JSON + SHA-256 + Ed25519 + separately pinned issuer trust.
- ADR-005: Persist decision + evidence + outbox atomically; anchor asynchronously.
- ADR-006 (2026-10-19): Project interpreter is Homebrew CPython 3.14.2 arm64 in `.venv`. Node is Homebrew `node@24` v24.22.0. Foundry is the official v1.8.5 `darwin_arm64` archive, checksum verified, installed under `~/.foundry/bin`. No Podman machine.
- ADR-007 (2026-10-19): Phase 01 storage driver is the standard-library `sqlite3` module. NetworkX, scikit-learn, and cryptographic libraries stay uninstalled. Test client is `httpx2` 2.14.0 because Starlette 1.9 deprecates the `httpx` test client. FastAPI 0.148.0 pulls `opentelemetry-api` as a library; auto-configuration stays off and no collector is run.
- ADR-008 (2026-10-19): Seed 42 scales are tiny 100/500, default 300/2,000, and benchmark 1,000/10,000. Benchmark and any larger count require an explicit confirmation and cannot exceed that cap. Reseed deletes only demo rows and requires `replace`. Public transaction and scoring reads omit ground-truth labels. Dataset fingerprint for seed 42 default is `cd1955ac9585643c7f67a7e12abc65dcfd905f135db7e21ef1f1d41680dc5ca0`.
- ADR-009 (2026-10-19): Phase 03 adds NetworkX 3.7 and scikit-learn 1.9.1 (NumPy 2.5.4, SciPy 1.18.1, joblib 1.6.0). Both stay lazy: importing the API does not import scikit-learn. The default score is `rules-v1`. `iforest-v1` is trained once on a separate legitimate population (seed 7) and combined as an experiment, not a probability. Chain receipts are not implemented.
- ADR-010 (2026-10-19): Phase 04 signs RFC 8785 canonical payload bytes with Ed25519 (`cryptography` 50.0.2, `rfc8785` 0.1.4) and hashes those same bytes with SHA-256. Strings are NFC-normalized before canonicalization. The pinned public-key registry is separate from the receipt. The private key is mode 0600 under gitignored `.local/keys`. Offline success is `SIGNATURE_VALID_OFFLINE`. The outbox row is `PENDING`; nothing is anchored.
- ADR-011 (2026-10-19): Phase 05 uses one native Anvil 1.8.5 process on 127.0.0.1:8545, chain id 31337, solc 0.8.28. `DecisionRegistry` keeps the first digest for a key and reverts on a different digest. Same-digest calls do not emit a second event. The ledger client checks chain id and runtime bytecode and does not send transactions. Anvil state in `.anvil/` is gitignored and is not durable evidence. Anvil sample keys are public test credentials and are not written to `.env.local`.
- ADR-012 (2026-10-19): Phase 06 anchors through one SQLite outbox row created in the same transaction as the decision and receipt. The worker polls one job at a time, backs off with jitter, and reads the contract before sending again. The same digest is confirmation. A different digest is a conflict. The independent CLI is `python -m veritas.verifier`. It does not call the scoring API. On-chain success is `VERIFIED_ONCHAIN`. An RPC outage is `VERIFICATION_UNAVAILABLE`.
- ADR-013 (2026-10-20): The dashboard is one Vite React page on 127.0.0.1:5173. It reads the existing API and posts a receipt copy to `POST /api/v1/verify`. That route does not score or store the copy. The graph hard limit is 100 nodes, and reaching it sets `truncated`. Private keys are not rendered. Anvil stays a resettable local chain.
- ADR-014 (2026-10-20): An RPC outage is a closed loopback URL or `RpcRoute.unavailable`. Anvil is left running so its blocks remain. The decision API still returns `anchor_status` `PENDING`. The worker records `RPC_UNAVAILABLE` and waits for `next_retry_at`. Recovery confirms the same digest once. `make benchmark` is the explicit 10k run. Published numbers are the files in `docs/benchmarks/`. A local Anvil commitment does not establish cross-bank governance.
- ADR-015 (2026-10-20): Phase 09 license is MIT (`LICENSE`, `license = "MIT"` in `backend/pyproject.toml`). All direct and transitive Python dependencies are permissive. The npm tree has 12 MPL-2.0 packages (`lightningcss`, a Vite build tool, not redistributed). CI installs from `backend/requirements.lock` and `frontend/package-lock.json`, pins actions to commit SHAs, and never starts Anvil. Anvil integration stays a local reproduction (`make test-e2e`, `make capture-tamper`). Publication text states there is no four-validator Besu QBFT, no independent institutions, synthetic data and labels, and no production fraud claim. No employer information is included or assumed to be approved for sharing.

## Per-phase handoff

```
Date: 2026-10-19
Phase: 02 — simulator and storage
State: ACCEPTED
Files changed:
  backend/veritas/storage/db.py, queries.py, sqlite.py, migrations/001_initial.sql
  backend/veritas/simulator/ (scales, validate, generate, store, cli)
  backend/veritas/api/scenarios.py, app.py
  backend/veritas/decisions/requests.py
  backend/tests/unit/test_simulator_storage.py
  backend/pyproject.toml, Makefile, README.md, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 17 passed in 0.60s
  make lint: All checks passed
  make format-check: 29 files already formatted
  make seed: accounts 300, transactions 2000, scenarios mule-ring-fan and pass-through-hops
    content_sha256 cd1955ac9585643c7f67a7e12abc65dcfd905f135db7e21ef1f1d41680dc5ca0
  make seed without REPLACE: CLI exit 3, "demo data already exists"; make reports error 2
  make seed REPLACE=1: same account count, transaction count, and content_sha256
  SQLite counts after reseed: banks 3, accounts 300, transactions 2000
Memory observation:
  vm.swapusage after the seed: total 3072.00M, used 2427.69M, free 644.31M
Acceptance criteria met:
  Default seed is exactly 300 accounts and 2,000 transactions.
  Two planted labeled scenarios exist and are omitted from transaction responses.
  Replay without replace does not wipe demo rows. Replay with replace reproduces the hash.
Blockers / residual risk:
  No Git commit yet.
  Benchmark scale was not executed in this phase; the cap and confirmation guard are tested.
  /api/v1/ready stays degraded until a later phase checks a chain.
Git commit ID: none
Next prompt: prompts/03-risk-graph.md
```

```
Date: 2026-10-19
Phase: 03 — bounded graph and experimental risk
State: ACCEPTED
Files changed:
  backend/veritas/graph/window.py, features.py
  backend/veritas/risk/rules.py, model.py, report.py
  backend/veritas/decisions/service.py
  backend/veritas/api/decisions.py, app.py, settings.py
  backend/veritas/storage/migrations/002_decision_explain.sql
  backend/tests/unit/test_risk_graph.py, test_simulator_storage.py
  backend/pyproject.toml, backend/requirements.lock
  README.md, .env.example, docs/RISK_REPORT.md, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 26 passed in 3.08s
  make lint: All checks passed
  make format-check: 37 files already formatted
  Rule-only synthetic report, seed 42 tiny: precision 0.0084, recall 0.25,
    true positive 3, false positive 353, false negative 9
  txn-000007: HIGH 100, reason codes FAN_OUT, HIGH_VELOCITY, RAPID_ONWARD,
    BANK_B to BANK_C, snapshot 11758b98649ba7447ee6aacf934f3c90d769004c1ec46547189dc3a574baee9c
  Same idempotency key replayed the same decision id, score, and snapshot digest
  txn-000011: REVIEW 55, MULTI_HOP and RAPID_ONWARD
  API import RSS 50577408 bytes; sklearn not imported
Memory observation:
  vm.swapusage after the report: total 3072.00M, used 2246.19M, free 825.81M
Acceptance criteria met:
  The completed cross-bank fan-out carries the fan-out and velocity reason codes.
  A second evaluate on a fresh database reproduced the score, codes, and snapshot digest.
  Decision responses do not include ground-truth labels. Receipt and anchor status are NOT_IMPLEMENTED.
Blockers / residual risk:
  No Git commit yet.
  On this tiny burst, ordinary accounts also reach the count thresholds, so precision is 0.0084.
  Chain anchoring and signed receipts remain unimplemented.
Git commit ID: none
Next prompt: prompts/04-evidence.md
```

```
Date: 2026-10-19
Phase: 04 — canonical signed evidence
State: ACCEPTED
Files changed:
  backend/veritas/evidence/canonical.py, models.py, keys.py, sign.py, verify.py
  backend/veritas/decisions/service.py
  backend/veritas/api/decisions.py, settings.py
  backend/veritas/risk/report.py
  backend/tests/unit/test_evidence.py, test_risk_graph.py
  backend/pyproject.toml, backend/requirements.lock
  .gitignore, .env.example, README.md, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 36 passed in 5.40s
  make lint: All checks passed
  make format-check: 43 files already formatted
  Exported receipt for txn-000007 verified as SIGNATURE_VALID_OFFLINE
  Changed risk score on a copy returned TAMPERED; the original still verified
  git check-ignore matches .local/keys/issuer.pem via .gitignore
  No project private-key file was present after the tests
  API import RSS 56033280 bytes; sklearn not imported
Memory observation:
  vm.swapusage after the tests: total 3072.00M, used 2401.00M, free 671.00M
Acceptance criteria met:
  A signed receipt is exported from GET /api/v1/decisions/{id}/receipt.
  The offline verifier accepts the unmodified receipt and rejects tampered copies.
  The private key is mode 0600 and the .local/keys path is gitignored.
Blockers / residual risk:
  No Git commit yet.
  Anchor jobs stay PENDING. There is no chain verification in this phase.
Git commit ID: none
Next prompt: prompts/05-anvil-contract.md
```

```
Date: 2026-10-19
Phase: 05 — local Anvil DecisionRegistry
State: ACCEPTED
Files changed:
  contracts/src/DecisionRegistry.sol, test/DecisionRegistry.t.sol, foundry.toml
  contracts/fixtures/anvil-public-dev.json, DecisionRegistry.build.json
  contracts/script/deploy-local.sh
  backend/veritas/ledger/client.py
  backend/tests/unit/test_ledger_client.py
  Makefile, README.md, .env.example, .gitignore, docs/STATUS.md
Commands/tests executed and actual results:
  make contract-test: 9 passed
  make test-unit: 40 passed in 6.29s
  make lint: All checks passed
  make format-check: 45 files already formatted
  anvil 1.8.5 listened on 127.0.0.1:8545, chain id 31337
  deployed 0x5FbDB2315678afecb367f032d93F642f64180aa3
  deploy tx 0x679c62b3a811625b1901e94c7e8e8703a93f26046094267c35828dfea997bca7
  runtime bytecode 1273 bytes, sha256 9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db
  same digest accepted, different digest reverted, unauthorized writer reverted
  ledger client read the stored commitment from the deployer at block 2
  Anvil stopped; port 8545 free. .env.local has no sample private key
Memory observation:
  vm.swapusage after the deploy: total 3072.00M, used 2458.50M, free 613.50M
Acceptance criteria met:
  Native Anvil served loopback RPC.
  The contract stored a commitment and enforced the anchor-writer role.
  Chain id and runtime bytecode were checked before the read.
Blockers / residual risk:
  No Git commit yet.
  No outbox worker. Decisions stay PENDING until the next phase submits them.
  Deleting .anvil/ erases the local chain.
Git commit ID: none
Next prompt: prompts/06-worker-and-verifier.md
```

```
Date: 2026-10-19
Phase: 06 — outbox worker and independent verifier
State: ACCEPTED
Files changed:
  backend/veritas/workers/outbox.py, anchor.py
  backend/veritas/verifier/check.py, __main__.py
  backend/veritas/ledger/client.py, commitment.py
  backend/veritas/decisions/service.py
  backend/veritas/api/decisions.py
  backend/tests/unit/test_outbox_verifier.py
  backend/tests/e2e/test_live_anchor.py
  Makefile, README.md, backend/pyproject.toml, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 46 passed in 37.13s
  make test-e2e: 1 passed in 2.70s
  make lint: All checks passed
  make format-check: 52 files already formatted
  Live fresh receipt anchored and the independent check returned VERIFIED_ONCHAIN
  A copy with a changed reason list returned TAMPERED
  After Anvil stopped, the same receipt returned VERIFICATION_UNAVAILABLE
  Port 8545 was free after the test
Memory observation:
  vm.swapusage after the unit tests: total 3072.00M, used 2750.56M, free 321.44M
Acceptance criteria met:
  Decision, signed receipt, and one outbox job are stored in one SQLite transaction.
  The worker confirmed the on-chain digest and did not report success during the outage.
  The verifier CLI does not call the scoring API.
Blockers / residual risk:
  No Git commit yet.
  The worker submits through Anvil's unlocked sample account. That account is a public test credential.
  Swap was 2750.56M of 3072.00M after the unit run. Do not start the API, Anvil, and a browser together.
Git commit ID: none
Next prompt: prompts/07-dashboard.md
```

```
Date: 2026-10-20
Phase: 07 — lightweight React dashboard
State: ACCEPTED
Files changed:
  frontend/ (Vite React TypeScript, Cytoscape, Vitest)
  backend/veritas/api/verify.py, settings.py, app.py
  backend/veritas/graph/features.py
  backend/tests/unit/test_verify_copy.py, test_risk_graph.py
  Makefile, README.md, .env.example, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 48 passed in 7.14s
  make lint: All checks passed
  make format-check: 54 files already formatted
  make frontend-test: 4 passed
  make frontend-build: succeeded (Vite 8.3.4)
  Browser at http://127.0.0.1:5173 against the seed-42 database:
    overview showed 300 accounts and 2000 transactions
    transactions page showed 50 of 2000
    txn-000007 scored HIGH 100 with FAN_OUT, HIGH_VELOCITY, RAPID_ONWARD
    stored receipt score stayed 100; a copy scored 1 returned Signature mismatch and stored=false
    txn-000500 drew 100 of 100 nodes with the truncation warning
    txn-missing returned "That record was not found."
  API, Vite, and port 8545 were free afterward
Memory observation:
  During the demo: API RSS about 21 MB, Vite RSS about 9.5 MB, page JS heap about 21 MB
  vm.swapusage after the unit tests: total 4096.00M, used 3053.75M, free 1042.25M
Acceptance criteria met:
  The five cards render live API data in the browser.
  The graph stops at 100 nodes and shows the truncation warning.
  The tamper control edits a copy and leaves the stored digest unchanged.
Blockers / residual risk:
  No Git commit yet.
  Anvil was not running, so the live receipt stayed Pending anchor.
  Swap was 3053.75M of 4096.00M. Do not start the API, Anvil, and the browser together.
Git commit ID: none
Next prompt: prompts/08-resilience-benchmark.md
```

```
Date: 2026-10-20
Phase: 08 — resilience and benchmarks
State: ACCEPTED
Files changed:
  backend/veritas/ledger/client.py
  backend/veritas/bench/study.py, chain.py, compare.py, __main__.py
  backend/tests/unit/test_resilience.py
  backend/tests/e2e/test_rpc_route.py
  docs/benchmarks/study.json, study.csv, COMPARISON.md
  Makefile, README.md, .gitignore, docs/STATUS.md
Commands/tests executed and actual results:
  make test-unit: 51 passed in 6.90s
  make test-e2e: 2 passed in 3.82s
  make lint: All checks passed
  make format-check: 61 files already formatted
  make benchmark: 17 rows, chain_measured true, seed 42, git revision none
    10k generation p50 171.542 ms, 1000 accounts, 10000 transactions
    default graph score p50 6.175 ms, p95 10.109 ms, p99 10.109 ms
    anchor confirmation p50 60.161 ms, n=1
    peak RSS 81543168 bytes
  Closed-port outage returned RPC_UNAVAILABLE and PENDING, then one CONFIRMED anchor.
  Anvil's process stayed up and the block number did not decrease.
  Port 8545 was free afterward
Memory observation:
  vm.swapusage after the benchmark: total 4096.00M, used 3158.00M, free 938.00M
Acceptance criteria met:
  Scoring returns a pending decision while RPC is routed away.
  Recovery anchors once and does not send a second commitment.
  The benchmark files are from the executed run and state the local-chain limit.
Blockers / residual risk:
  No Git commit yet.
  Anchor timing is one sample. p95 and p99 match on 15-sample rows when nearest-rank lands on the same observation.
  Graph score timing includes the capped window, not every one of the 10,000 transactions.
Git commit ID: none
Next prompt: prompts/09-publication-release.md
```

```
Date: 2026-10-20
Phase: 09 — reproducible release and LinkedIn follow-up
State: PREPARED, NOT ACCEPTED (awaiting approval)
Files changed:
  README.md, SECURITY.md, CONTRIBUTING.md, .gitignore (*.egg-info/), Makefile (capture-tamper)
  .github/workflows/ci.yml (SHA-pinned actions, locked installs, read-only permissions)
  backend/pyproject.toml (license), backend/scripts/capture_tamper_evidence.py
  docs/API.md, docs/PROTOCOL.md (verifier statuses, version policy, contract identity)
  docs/ARCHITECTURE.md (section 15, as-built Mermaid), docs/ENVIRONMENT.md (path redacted)
  docs/ACCEPTANCE.md (PASS/FAIL/NOT EXECUTED), docs/STATUS.md
  docs/publication/: linkedin-followup.md, storyboard.md, tamper-cli-live.txt, RELEASE_NOTES.md,
    THIRD_PARTY.md, SECRET_SCAN.md, secret-scan.txt
  Reviewed and kept from an earlier Phase 09 pass: LICENSE, .env.example, docs/RUNBOOK.md,
    THREAT_MODEL.md, adr/001-003, openapi.json, images/*.png, tamper-cli.txt
Commands/tests executed and actual results:
  make test-unit: 51 passed
  make lint: All checks passed
  make format-check: 62 files already formatted
  make contract-test: 9 passed
  make frontend-test: 4 passed; make frontend-build: succeeded
  make test-e2e: 2 passed
  make capture-tamper: original VERIFIED_ONCHAIN (exit 0); copy with risk_score 100 to 1
    TAMPERED (exit 1); wrong contract CONFIG_MISMATCH (exit 1); Anvil stopped
    VERIFICATION_UNAVAILABLE (exit 1). Anchor CONFIRMED at block 4.
  docs/openapi.json equals app.openapi() output
  Runtime bytecode sha256 in the build fixture equals the documented 9bef8ceb...78db
  Secret scan: 148 publish-set files, no private key, token pattern, or sensitive file type;
    only Anvil's two public development keys, in the fixture
  License audit: no GPL/LGPL/AGPL in Python; 12 MPL-2.0 npm build-tool packages (lightningcss)
  Ports 8000, 5173, 8545 were free afterward
Acceptance criteria met:
  docs/ACCEPTANCE.md: 32 PASS, 0 FAIL, 2 NOT EXECUTED (UI-02, PUB-01)
Blockers / residual risk:
  PUB-01 clean checkout is NOT EXECUTED. It needs approval for a temporary project-owned directory.
  The CI install path (requirements.lock, Python 3.14.2, forge-std v1.9.6) and the workflow
    itself have never run on GitHub. Python 3.14.2 availability on the runner is unverified.
  UI-02: the dashboard has not been run with an anchored receipt. Fraud-ring graph for
    txn-000007 was not screenshotted. No video was recorded; storyboard only.
  Secret scan is a pattern scan. No dedicated scanner was installed, and there is no git history.
  Anchor confirmation timing is one sample (n=1).
  Rule-only precision is 0.0084 on the tiny seed. The article leads with that result.
  The publish set (148 files) includes .cursor/, prompts/, and the master plan. Decide whether
    to ship them.
  Author-facing placeholders remain in linkedin-followup.md (original-article link, repo link).
  Swap was about 5.3 GB of 6 GB during Phase 09. Processes were run one at a time.
Git commit ID: none
Next step: approval decisions listed in the final Phase 09 message
```

Never mark ACCEPTED on tests that have not been run.
