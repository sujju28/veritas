# I Wrote About On-Chain Intelligence in Banking. Then I Built a Verifiable Fraud-Decision Prototype.

> **DRAFT. Not published.** Bracketed items are for the author to fill in. Do not post until the repository is public, the numbers table at the end still matches `docs/benchmarks/`, and you are sure nothing here involves an employer or its information.

## Why I built it

[Author: one or two sentences linking to the earlier article and restating its hypothesis in your own words. The repository does not contain that text, so it is not paraphrased here.]

The question I wanted to test was narrow: if a fraud decision is signed, and a digest of it is written to a chain, can someone **other than the scorer** detect that the decision was altered afterwards? And what does the chain add compared with a signed log in a database?

## What I built

A local prototype that runs as native processes on an 8 GB Apple Silicon MacBook Pro (M1, macOS, Python 3.14.2, Node 24, Foundry 1.8.5):

- A seeded generator for three **simulated** banks. At the default seed-42 scale it writes 300 accounts and 2,000 transfers, with two planted laundering patterns.
- A bounded transaction graph and a rule-based score (`rules-v1`) with reason codes. An optional anomaly model exists as an experiment and is not a probability.
- A signed decision receipt: RFC 8785 canonical JSON, SHA-256, Ed25519 over those bytes, with the public key pinned separately from the receipt.
- A small Solidity registry on one native Anvil process (chain id 31337) that stores only a 32-byte decision key and a 32-byte evidence digest. No account data goes on-chain.
- An outbox so the API never waits for the chain, and an independent verifier CLI that does not call the scoring API.
- A small dashboard.

It ships with 51 backend unit tests, 9 Foundry tests, 4 frontend tests, and 2 integration tests against a live local Anvil. I ran all of them before writing this.

## What the fraud scoring actually did

I will lead with the unflattering result. On the tiny seed-42 set (100 accounts, 500 transfers, 12 transfers labeled as part of a planted pattern), the rule-only report flagged 356 transfers. Three were true positives and 353 were false positives. Precision was **0.0084** and recall was **0.25**.

The planted cross-bank fan-out (`txn-000007`) scored HIGH 100 with `FAN_OUT`, `HIGH_VELOCITY`, and `RAPID_ONWARD`, and that part works as designed. But the legitimate background traffic in my generator is dense: 488 transfers inside one 15-minute window, so many ordinary accounts also reach four counterparties. The thresholds fire on them too.

The labels are ones my own generator planted. This says nothing about how any rule or model would behave on real payments, and I am not claiming it does.

## What the receipt and the chain showed

I scored `txn-000007`, anchored its receipt to the local chain, and ran the verifier on four things. Raw output is in `docs/publication/tamper-cli-live.txt`.

| Case | Result | Exit |
|---|---|---|
| Original receipt, chain running | `VERIFIED_ONCHAIN` | 0 |
| Copy with `risk_score` changed from 100 to 1 | `TAMPERED` | 1 |
| Original, wrong contract address | `CONFIG_MISMATCH` | 1 |
| Original, Anvil stopped | `VERIFICATION_UNAVAILABLE` | 1 |

The tampered copy fails on the digest before any chain call. The last row matters to me as much as the first: when the RPC is down, the verifier says it cannot verify. It never says "verified".

What this proves is limited. It shows a receipt was not changed after signing, and that the chain holds the same digest. It does **not** show the decision was correct.

## Signed log versus local chain: what I measured

All numbers are from one run on my laptop (seed 42, 2 warm-up calls discarded, 15 samples unless stated, nearest-rank percentiles):

- Graph scoring at the default scale: p50 6.175 ms, p95 10.109 ms.
- Canonicalizing a receipt: p50 0.019 ms. Signing: p50 0.050 ms. Offline verification: p50 0.112 ms.
- One anchor confirmation on local Anvil: 60.161 ms. **That is a single sample (n=1)**, so treat it as an order of magnitude, not a distribution.
- One contract lookup over RPC (`getDecision` for a key that is not stored): p50 0.826 ms, p95 32.523 ms.
- Generating the 1,000-account / 10,000-transaction dataset: 171.542 ms (one sample). Peak process memory during the study was 81,543,168 bytes.

Graph scoring reads a capped lookback window, so a larger dataset costs more to generate but does not make one score proportionally slower. I did not measure scoring across all 10,000 transactions.

Both approaches detect an unauthorized change to a signed field. Neither detects a change re-signed by whoever holds the issuer key. The local chain added a second process, a writer role, confirmation latency, and an outage path. **On this setup it added no protection against the person running it**, because one person controls the signer, the database, the worker, and the chain, and can reset Anvil.

## What this is not

- **Not a four-validator Besu QBFT network.** One native Anvil process, by design, to fit 8 GB.
- **No institutionally independent nodes.** Nothing here shows what multi-bank governance would give you.
- **Synthetic data and synthetic labels.** No real banking data and no customer data.
- **Not a production fraud claim.** The precision above is the evidence.
- Local Anvil is resettable. A commitment on it is not durable evidence.

## Where I would take it next

The interesting claim is the one I could not test: a permissioned multi-node EVM network where different organizations run the validators, so that no single party can rewrite the record. That would need real governance, independent key custody, and a privacy design for what banks are willing to share. A local prototype cannot stand in for any of that. [Author: add your own view on research direction.]

## Reproduce it

[Repository link: add after publishing is approved.] The README gives the setup for an 8 GB M1, the startup order, the seed-42 demo command, and a `make capture-tamper` target that regenerates the verifier transcript. Raw benchmark files are `docs/benchmarks/study.json` and `study.csv`. CI runs Python unit tests, the frontend build, and Foundry tests. The live-chain integration is reproduced locally, not in CI. [Author: add short video link only if you record one; none exists yet.]

---

## Numbers and where they come from (remove before posting)

| Figure in the article | Source |
|---|---|
| 300 accounts, 2,000 transfers, seed 42 | `docs/STATUS.md` Phase 02; `docs/benchmarks/study.csv` (`default` rows) |
| Precision 0.0084, recall 0.25, 356 flagged, TP 3, FP 353, FN 9, 12 labeled | `docs/RISK_REPORT.md` |
| 488 background transfers in one 15-minute window | `docs/RISK_REPORT.md` |
| `txn-000007` HIGH 100 with three reason codes | `docs/RISK_REPORT.md`; `docs/publication/images/decision.png` |
| Verifier results and exit codes | `docs/publication/tamper-cli-live.txt` |
| graph_score default p50 6.175 / p95 10.109 ms | `docs/benchmarks/study.csv` row `default,graph_score` |
| canonical p50 0.019, sign p50 0.050, offline_verify p50 0.112 ms | `study.csv` rows `default,canonical`, `default,sign`, `default,offline_verify` (0.0187, 0.0499, 0.1120 ms) |
| anchor_confirm 60.161 ms, n=1 | `study.csv` row `chain,anchor_confirm` |
| rpc_read p50 0.826 / p95 32.523 ms (`getDecision` on an absent key, `backend/veritas/bench/chain.py`) | `study.csv` row `chain,rpc_read` |
| dataset_generate 171.542 ms, 1,000 / 10,000 | `study.csv` row `benchmark,dataset_generate` (n=1) |
| Peak RSS 81,543,168 bytes | `study.csv` / `study.json` `rss_bytes` |
| Hardware, OS, Python | `study.json`: `arm64`, 8,589,934,592 bytes RAM, `macOS-26.6.2-arm64-arm-64bit-Mach-O`, Python 3.14.2 |
| 51 / 9 / 4 / 2 tests | `docs/STATUS.md` Phase 09 entry (executed 2026-10-20) |

Author checklist before posting:

1. The repository is public and the link works.
2. The statement that nothing here involves your employer is true for you. This draft makes no claim about an employer, and the repository must not mention one.
3. `docs/benchmarks/` was not regenerated since the numbers above were copied. If it was, update the article.
4. You are comfortable with the unflattering precision result as the lead finding.
