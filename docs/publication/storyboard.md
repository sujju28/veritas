# Demo storyboard (3–5 minutes)

This is a storyboard, not a recording. **No video file exists.** Every scene below names the artifact in this repository that backs it, and scenes without a real capture are marked. Narrate only what the artifact shows.

Recording setup: follow `README.md` (startup order). On an 8 GB machine, record the dashboard scenes first with the chain stopped, then stop the dashboard and record the terminal scenes. Do not run the API, Vite, a browser, Anvil, and a screen recorder together.

| Time | Scene | What to show | Backed by | Capture status |
|---|---|---|---|---|
| 00:00–00:30 | Thesis | Dashboard header: "Synthetic local data. Anvil is a resettable development chain, not a permissioned QBFT ledger." Overview card: seed 42, 300 accounts, 2,000 transactions, two planted scenarios | `images/overview.png` | Captured from the running app |
| 00:30–01:30 | Fraud ring | Score `txn-000007`: HIGH 100, `FAN_OUT`, `HIGH_VELOCITY`, `RAPID_ONWARD`, with values against thresholds | `images/decision.png` | Captured from the running app |
| | | Bounded graph. The existing capture is `txn-000500`, which hits the 100-node limit and shows the truncation warning. It demonstrates the cap, **not** the fraud ring | `images/graph.png` | Captured. A graph centred on `txn-000007` is **not captured** |
| 01:30–02:15 | Decision receipt | Decision id, score, reason codes, feature digest `11758b98…baee9c`, receipt digest, signer `issuer-local-1 Ed25519`. Anchor shows "Pending anchor" and no transaction, because no chain was running | `images/receipt-result.png` | Captured from the running app |
| 02:15–03:00 | Chain | Deploy line with the contract address and runtime hash, then anchor outcome `CONFIRMED` with tx hash and block number, from a real run | `tamper-cli-live.txt` header lines | Captured as terminal text. A dashboard showing an anchored receipt is **not captured** |
| 03:00–03:45 | Tamper test | Original receipt: `VERIFIED_ONCHAIN`, exit 0. Copy with `risk_score` 100 → 1: `TAMPERED`, exit 1. Browser version of the same edit: "Signature mismatch", `stored=false` | `tamper-cli-live.txt` sections 1–2, `images/receipt-result.png` | Captured. Say plainly: this shows the receipt was not altered, not that the decision was right |
| 03:45–04:30 | Outage | Original receipt with Anvil stopped: `VERIFICATION_UNAVAILABLE`, never "verified". Wrong contract address: `CONFIG_MISMATCH`. For the scoring path, cite the executed outage test | `tamper-cli-live.txt` sections 3–4, `backend/tests/e2e/test_rpc_route.py` | Terminal text captured. Dashboard footage of an outage is **not captured** |
| 04:30–05:00 | Trust models | Signed local log vs local Anvil table. Close on what the local chain cannot show | `docs/benchmarks/COMPARISON.md` | Document only |

## Lines to say, and lines not to say

Say: one operator controls the signer, database, worker, and chain. The data is synthetic. The score is an experiment. Anvil can be reset.

Do not say: that this is a consortium, that nodes are independent, that results transfer to a bank, or that the model detects fraud in production.

## Raw material

- Screenshots: `docs/publication/images/`
- Terminal evidence: `docs/publication/tamper-cli-live.txt` (live chain, regenerate with `make capture-tamper`) and `docs/publication/tamper-cli.txt` (earlier run with a closed RPC port, tamper and unavailable cases only)
- Raw measurements: `docs/benchmarks/study.json`, `docs/benchmarks/study.csv`
