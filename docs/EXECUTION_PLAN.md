# Cursor-Executable Engineering Plan — Project VERITAS Core MVP

## A. Delivery contract

**Hardware:** MacBook Pro M1 / 8 GB; prefer low-memory, native ARM64 toolchains. **Software:** Python 3.12+ in `.venv`, FastAPI, SQLAlchemy (or `sqlite3`), SQLite WAL, NetworkX, scikit-learn, `cryptography` Ed25519, RFC 8785 canonical JSON library with pinned dependency, Web3.py, Foundry/Anvil, Solidity, React/Vite/TypeScript and Cytoscape.js. Avoid heavy libraries unless profiling justifies. Optional SQLite migration using Alembic or simple numbered SQL migrations.

**Delivery mode:** One Cursor Agent phase prompt per chat or checkpoint; DO NOT ask Cursor to generate the entire application in a single answer. Phase prompts include file scope, tests, validation and stop condition. Track each in `docs/STATUS.md` and commit at phase gates.

**Estimated effort:** 15–25 focused working days of development + verification (not guaranteed); baseline optimized for solo AI-assisted development. M1 memory and tool setup may add time. There is no promise of unattended, background completion.

## B. Prerequisites and environment check (before code)

1. `uname -m` should report `arm64`; `sysctl -n hw.memsize` ~8 GB. Verify disk free (`df -h .`) — target 15–20 GB free for toolchains, builds and Git.
2. `python3 --version` (select consistent supported minor release), `node --version` (current LTS), `npm --version`, `git --version`, `xcode-select -p`.
3. `forge --version`, `cast --version`, `anvil --version`. Install Foundry via vetted official instructions; prefer native builds/binaries. If installers fail under ARM64, document problem, do not switch to x86 emulation without approval.
4. `podman machine ls`: **do not start existing heavy Podman VMs**. Podman is optional; we use native development primarily.
5. Capture `memory_pressure`, `vm_stat` and `top -l 1 -o mem` snapshots before/after running development stack (commands might differ by macOS release). Avoid secrets in logs.
6. Verify local port availability for API 8000, Vite 5173 and Anvil RPC 8545. Bind all to 127.0.0.1.

## C. Phase-to-prompt mapping

| Phase | Workdays* | Cursor prompt | Minimum exit gate |
|---|---:|---|---|
| 00 | 0.5–1 | `prompts/00-machine-preflight.md` | Tooling report + no unnecessary VM/containers |
| 01 | 1–2 | `prompts/01-repo-and-api.md` | `make test-unit` + `/health` work |
| 02 | 2–3 | `prompts/02-simulator-storage.md` | Seeded default dataset identical across runs; ground truth isolated |
| 03 | 2–3 | `prompts/03-risk-graph.md` | Fraud patterns detected with reasons + held-out test report |
| 04 | 2–3 | `prompts/04-evidence.md` | Tamper-proof signed receipt tests |
| 05 | 2–3 | `prompts/05-anvil-contract.md` | Foundry tests + local contract writes/reads |
| 06 | 2–3 | `prompts/06-worker-and-verifier.md` | End-to-end signed receipt → on-chain → independent verify |
| 07 | 2–3 | `prompts/07-dashboard.md` | UI live demo and controlled graph limits |
| 08 | 1–2 | `prompts/08-resilience-benchmark.md` | Outage/recovery + real benchmark CSV |
| 09 | 1–2 | `prompts/09-publication-release.md` | Clean setup, license, tests, screenshots, article draft |

*Effort bands overlap with integration/bug fixing; total planning estimate 15–25 focused days, not a contractual estimate.

## D. Gates / failure policy

At the end of EVERY phase:

1. Run exactly the relevant unit/integration/contract test commands and show pass/fail summaries.
2. Provide `git diff --stat`, list changed files and note unresolved dependencies.
3. Record memory/CPU observation during load for phases 03 onward.
4. Update `docs/STATUS.md`: phase state, tests, blockers, next prompt, decisions.
5. Stop. Do **not** implement the next phase until developer reviews and approves.
6. On failure, fix within same phase; never report successful acceptance without executed evidence. Commit reviewed changes on local Git.
7. If the environment prevents running commands, say **NOT EXECUTED**, specify exact missing prerequisite; do not invent a test result.

## E. API service / artifact layout

```text
veritas-cursor-m1/
  .cursor/rules/*.mdc
  .cursor/commands/*.md
  prompts/00..09*.md
  docs/ARCHITECTURE.md
  docs/EXECUTION_PLAN.md
  docs/ACCEPTANCE.md
  docs/PUBLICATION.md
  docs/STATUS.md
  backend/
    pyproject.toml
    veritas/{api,simulator,storage,graph,risk,decisions,evidence,ledger,workers,verifier}/
    tests/{unit,integration,e2e}/
  frontend/
    package.json
    src/{api,components,pages,styles}/
  contracts/
    foundry.toml
    src/DecisionRegistry.sol
    test/DecisionRegistry.t.sol
    script/Deploy.s.sol
  datasets/synthetic/README.md
  scripts/
  .env.example
  .gitignore
  Makefile
  README.md
  LICENSE
  SECURITY.md
  CONTRIBUTING.md
```

## F. Incremental implementation order

**Vertical slice first:** synthetic transaction → decision → canonical receipt → signature → Anvil commitment → independent CLI verification → tamper failure. A fully interactive graph/dash comes after the trust proof works. Phase 03 scoring can begin rules-only with anomaly score optional and then add IsolationForest once feature testing is robust.

**Baseline data size:** three logical banks, 300 synthetic accounts, 2,000 transactions including at least two planted fraud ring patterns and legitimate comparators. `--scale benchmark` goes to 10,000 without retaining enormous graph visual data in browser.

**No heavy runtime**: no Podman machine for default demo, no Postgres/Besu containers, no Kafka, no Kafka-compatible alternatives, no Spark, no external model inference.

## G. Proposed run commands to implement

These commands are **targets Cursor must create**, not guaranteed working in the current planning package:

```bash
make setup          # python venv/npm deps/Foundry validation; no destructive operations
make contract-test  # forge test
make chain-start    # native anvil; manual persistent terminal is OK
make contract-deploy
make backend        # uvicorn one worker, 127.0.0.1:8000
make worker         # small outbox worker with bounded poll interval
make frontend       # Vite dev server, 127.0.0.1:5173
make seed           # seeded 300/2000 default dataset
make test-unit
make test-integration
make test-e2e
make demo
make benchmark
make verify
```

Use two or three Terminal tabs; do not have Cursor spawn several duplicate service processes inadvertently. Process management instructions should explain how to stop all processes gracefully.

## H. Scoring / evidence acceptance thresholds

See `docs/ACCEPTANCE.md` for executable test names. Suggested release goals: 100% of seeded tampering variants rejected; independent CLI verifies unmodified receipts; async decision API still works during RPC outage; 0 PII-like fields on-chain; minimal runtime memory footprint demonstrable; false positive and fraud ring recall publicly measured on synthetic scenarios. No invented F1/latency claims.

## I. Local hardware fallback order

If memory pressure rises: (1) close browser tabs and other dev apps; (2) stop frontend during test/benchmark; (3) run 100 accounts/500 transactions tiny set; (4) disable ML model temporarily and confirm rule-only mode; (5) reduce graph max nodes; (6) run tests serially; (7) split dashboard and chain demos into sequential modes. Do not solve an M1 memory problem by adding more containers or a larger LLM.

## J. Version pinning and reproducibility

- At setup select current stable compatible tool versions and **pin exact version or bounded major/minor** in lockfiles and README; do not hardcode guessed package versions before tool inspection.
- Commit backend lock/environment metadata, frontend lockfile, Foundry config and contract bytecode hash (or artifact checksum).
- Preserve one end-to-end reproducible smoke dataset and documented one-command (or few-command) demonstration.
- Lock contract address and chain ID in generated `.env.local`, never commit private secrets; publish safe `.env.example` only.

## K. Release checklist ownership

Agent does code and evidence capture; developer approves security choices, licenses, performance claims, repository publication and LinkedIn article. GitHub publishing and any external network operations require explicit user permission.
