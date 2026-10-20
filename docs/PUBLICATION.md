# Publishable VERITAS Prototype — Demonstration, Evidence, LinkedIn Article

## A. Demo scenes / storyboard (record 3–5 minutes)

**00:00–00:30 — Thesis.** Local multi-bank synthetic transactions; explain the boundary of local Anvil.
**00:30–01:30 — Fraud ring.** Choose seeded cross-bank mule ring; animate limited account graph and highlights; show graph features and rule/model reasons.
**01:30–02:15 — Decision receipt.** Open decision ID, model/rules version, reason codes, feature snapshot hash, issuer key ID and cryptographic digest.
**02:15–03:00 — Chain.** Show actual Anvil transaction hash, contract state, signed evidence matching chain commitment; record block info.
**03:00–03:45 — Tamper test.** Edit a *copy* of the receipt; independent CLI fails; original passes. Explain that this shows integrity, not decision correctness.
**03:45–04:30 — Outage.** Pause RPC access (without deleting chain state), produce decision as PENDING, restore and verify replay.
**04:30–05:00 — Compare trust models.** Signed database audit log vs local chain: honest operational/latency trade-offs; future multi-institution governance.

## B. Benchmark methodology

- Record machine hardware, OS, Python, Node, Foundry versions, dataset seed, number of accounts/transactions, sampling method and temperature/background load if known.
- Use `time.perf_counter()` and capture p50/p95/p99 for scoring, canonicalization, signing, offline verification, RPC lookup, anchoring confirmation. Use at least 3 runs after warm-up; report sample count.
- Record RSS (`resource` or `psutil` if permitted) and optional macOS `memory_pressure` snapshot. Explicitly state whether Cursor, browser, Anvil and frontend were running concurrently.
- Use comparable trust semantics: signed-audit-log baseline **can** verify tampering with trusted keys, but cannot by itself provide independently governed append-only ledger consensus. Local Anvil also **does not** provide institutional consensus; avoid claiming it does.
- Publish actual raw CSV/JSON and a notebook-free summary with charts optional. No invented numbers.

## C. Suggested README sections

Motivation; one-sentence limitation statement; screenshot; setup; quick demo; technical architecture; APIs; how signing and commitments work; threat model; benchmark results; reproducibility; local chain reset behavior; future upgrades; license; security; contribution guidelines.

## D. GitHub release audit

- `LICENSE` MIT or Apache 2.0 (choose and verify compatibility), third-party notices if needed.
- `SECURITY.md`: research/demo only, no real customer data, no actual private bank keys.
- `.gitignore`: secrets, `.env*` except `.env.example`, `.venv`, `node_modules`, chain state and DB; no untracked accidental key material.
- Detect license obligations for included Solidity and Python/Node packages.
- GitHub Actions must run unit, contract and frontend build separately; use ARM64 compatibility notes for users on x86.
- No public repository push until user authorizes it.

## E. LinkedIn follow-up article working outline

**Title:** "I Wrote About On-Chain Intelligence in Banking. Then I Built a Verifiable Fraud-Decision Prototype."

1. Original hypothesis about trust, explainability and blockchain.
2. What was built on an 8 GB Apple Silicon laptop; why modular monolith/native processes.
3. Fraud-ring intelligence across three **simulated** banks, detection limits and measured metrics.
4. Signed evidence receipt + reproducible hash/signature + contract commitment.
5. Demonstrate a tampering attempt and independent verification.
6. Signed-log comparison: what the blockchain contributed, and what **local Anvil cannot prove**.
7. Limitations: no genuine bank-to-bank security boundary, decentralized governance, federated privacy or real-world detection performance.
8. Research path: deploy a permissioned multi-node EVM network controlled by different organizations, privacy-safe collaboration, verifiable KYC.
9. Source repo, architecture diagram, short video, reproducible data/benchmark link.

**Publish only after** success criteria are demonstrated in actual terminal logs and verified repository setup, not on developer estimates.
