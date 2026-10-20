# Project VERITAS — MVP Acceptance Specification

Each acceptance test is actionable and should be automated wherever feasible. Results below were reviewed in Phase 09 on 2026-10-20. Status is **PASS**, **FAIL**, or **NOT EXECUTED**. PASS means the named test or recorded run executed and met the expected result. Where the evidence covers only part of the criterion, the note says exactly which part. Phase 09 re-ran on this host: `make test-unit` (51 passed), `make lint`, `make format-check` (62 files), `make contract-test` (9 passed), `make frontend-test` (4 passed), `make frontend-build`, `make test-e2e` (2 passed), and `make capture-tamper`.

| ID | Test / stimulus | Expected result | Primary phase | Status | Evidence and notes |
|---|---|---|---|---|---|
| ENV-01 | Detect host architecture and physical RAM | ARM64 Mac, ~8 GB; native tooling documented | 00 | PASS | `docs/ENVIRONMENT.md`: arm64, `hw.memsize` 8589934592. Benchmark `study.json` records the same |
| ENV-02 | Run default local demo without Podman | Vite/API/Anvil function as host processes | 07 | PASS | No Podman anywhere. API plus Vite ran together (Phase 07). Anvil ran separately (e2e, `make capture-tamper`). **All three were never run at once** because swap was near full on 8 GB |
| SIM-01 | Seed=42, default scale twice in clean DB | same normalized bank/account/transaction facts, same labels | 02 | PASS | `test_reseed_replays_the_same_hash_and_requires_replace`. Phase 02 `make seed REPLACE=1` gave the same `content_sha256` |
| SIM-02 | Two distinct fraud-ring fixtures with legit comparator | ground truth exists but not accessible from scoring queries | 02 | PASS | `test_planted_patterns_cross_banks_and_legitimate_rows_are_unlabeled`, `test_scoring_modules_do_not_read_ground_truth`, `test_cross_bank_fan_out_has_reason_codes_and_no_labels` |
| SIM-03 | Generate 10k benchmark dataset | completes without memory crash; measurement recorded | 08 | PASS | `make benchmark`: 1,000 accounts / 10,000 transactions, generation 171.542 ms (n=1), peak RSS 81,543,168 bytes. `docs/benchmarks/` |
| API-01 | Invalid account/amount/time payload | appropriate 4xx structured error; no DB corruption | 02 | PASS | `test_invalid_payload_does_not_write_and_reseed_keeps_downstream_rows`, `test_validation_error_is_structured`, `test_amounts_are_positive_integers_and_times_are_utc` |
| API-02 | Same decision request/idempotency key twice | same decision id; no duplicate evidence/outbox job | 06 | PASS | `test_idempotent_replay_and_conflicting_key`, `test_duplicate_outbox_and_confirm_without_a_second_submit` |
| RISK-01 | Injected fan-in/fan-out ring | graph features + expected reason codes | 03 | PASS | `txn-000007` HIGH 100 with `FAN_OUT`, `HIGH_VELOCITY`, `RAPID_ONWARD` (`test_cross_bank_fan_out_has_reason_codes_and_no_labels`, `docs/RISK_REPORT.md`) |
| RISK-02 | Shift timestamps / insert future transaction | scoring never reads events after evaluation time | 03 | PASS | `test_window_excludes_future_transfers`, `test_scoring_window_excludes_later_events` |
| RISK-03 | Separate training and test populations | metrics printed with seed and caveats | 03 | PASS | `test_hybrid_model_trains_once_on_a_separate_population` (seed 7 legit population), `test_synthetic_report_states_the_caveat`. Report records seed 42 tiny and precision 0.0084 / recall 0.25 |
| RISK-04 | No fabricated interpretation of anomaly score | response identifies model as anomaly not probability | 03 | PASS | Decision card shows `experimental_score` (`images/decision.png`). `docs/RISK_REPORT.md` states it is not a probability |
| EVD-01 | Sign canonical receipt, verify detached signature | pass for unmodified payload | 04 | PASS | `test_offline_verifier_accepts_original_and_rejects_tampering`, `test_exported_receipt_verifies_and_a_copy_does_not` |
| EVD-02 | Change field, key order, Unicode, number form | valid canonical equivalence allowed; altered values rejected | 04 | PASS | `test_field_order_unicode_and_number_form_share_bytes`, `test_equivalent_unicode_still_verifies`, `test_non_finite_numbers_are_rejected`, `test_digest_matches_across_processes` |
| EVD-03 | Replace signature or untrusted key | INVALID_SIGNATURE or UNKNOWN_ISSUER | 04 | PASS | `test_substituted_signature_and_unknown_signer` |
| EVD-04 | Check on-chain payload | no account IDs, feature payloads, PII or raw decisions | 05 | PASS | By construction: `anchorDecision(bytes32,bytes32)` takes only the decision key and digest, and the 9 Foundry tests pass. **No dedicated test inspects chain contents for personal data** |
| CHAIN-01 | Anchor valid digest as authorized address | contract stores key and digest; event emitted | 05 | PASS | Foundry `test_anchor_stores_commitment_and_emits_event`. Live anchor: `CONFIRMED` block 4 in `tamper-cli-live.txt` |
| CHAIN-02 | Re-anchor same key different digest | reject; prior digest unchanged | 05 | PASS | Foundry `test_different_digest_reverts`; `deploy-local.sh` asserts the revert on Anvil |
| CHAIN-03 | Unauthorized address anchors | revert | 05 | PASS | Foundry `test_unauthorized_address_reverts`, `test_revoked_writer_reverts`; `deploy-local.sh` asserts it on Anvil |
| CHAIN-04 | Fresh Anvil reset | not described as durable blockchain evidence | 05 | PASS | `test_chain_reset_and_contract_rejection` (reset is not confirmation). Wording in `README.md`, `SECURITY.md`, `THREAT_MODEL.md`, and the dashboard banner |
| OUT-01 | Worker stopped, decision created | valid decision with PENDING_ANCHOR | 06 | PASS | Status string is `PENDING` (`anchor_status`), shown as "Pending anchor" in `images/decision.png`. `test_decision_stays_pending_and_recovery_anchors_once` |
| OUT-02 | Worker crash after submission, before mark | restart reconciles; no contradictory duplicate commitments | 06 | PASS | `test_restart_confirms_a_submitted_job_and_conflict_stops`, `test_two_workers_claim_one_job`. Simulated with a fake chain in unit tests, not a killed OS process |
| OUT-03 | RPC outage (prefer proxy disable, not chain reset) | decision succeeds, job queued, bounded retry; recovery anchored | 08 | PASS | e2e `test_closed_port_outage_recovers_without_resetting_anvil`, `test_rpc_outage_is_not_confirmation_and_waits`. Outage is a closed loopback port, not a proxy |
| VER-01 | Independent CLI with trusted public key and RPC | VERIFIED only if offline and chain checks pass | 06 | PASS | e2e `test_fresh_receipt_anchors_and_outage_is_not_success`. `tamper-cli-live.txt` case 1: `VERIFIED_ONCHAIN`, exit 0 |
| VER-02 | Wrong chain ID/contract | fail explicitly, never VERIFIED | 06 | PASS | `tamper-cli-live.txt` case 3: `CONFIG_MISMATCH`, exit 1. `test_chain_id_and_bytecode_must_match`. A wrong chain id was covered by the unit test only, not the live run |
| VER-03 | Anvil stopped, receipt valid | VERIFICATION_UNAVAILABLE or offline-only result | 06 | PASS | `tamper-cli-live.txt` case 4: `VERIFICATION_UNAVAILABLE`, exit 1 |
| VER-04 | Tampered receipt on CLI | TAMPERED / INVALID_SIGNATURE / ONCHAIN_MISMATCH as appropriate | 06 | PASS | `tamper-cli-live.txt` case 2: `TAMPERED`, exit 1. `ONCHAIN_MISMATCH` is covered by `test_verifier_statuses` only |
| UI-01 | Show selected seeded fraud ring | bounded visual graph and reason codes, no UI freeze | 07 | PASS | Browser demo (Phase 07): reason codes for `txn-000007`; graph stopped at 100 of 100 nodes with warning for `txn-000500`; vitest node cap test. **No screenshot of a graph centred on the `txn-000007` ring exists** |
| UI-02 | Show decision vs anchor status | PENDING / ANCHORED / error accurately displayed | 07 | NOT EXECUTED | Browser showed only "Pending anchor" and error text because Anvil was not running. The ANCHORED tag is covered only by the unit test `maps anchor and verifier results onto the demo tags`. No browser run with an anchored receipt |
| UI-03 | Trigger demo tamper on copy of receipt | original remains intact, tampered verification fails | 07 | PASS | `images/receipt-result.png`: copy score 1 gives "Signature mismatch", `stored=false`, stored digest unchanged. `test_tampered_copy_fails_and_stored_receipt_stays` |
| PERF-01 | Warm default scoring benchmark | p50/p95/p99 + memory + actual hardware details | 08 | PASS | `docs/benchmarks/study.json`: default graph_score p50 6.175 ms, p95 10.109 ms, p99 10.109 ms (n=15, 2 warm-ups). p95 equals p99 at n=15 |
| PERF-02 | Signed log vs on-chain benchmark | reports trust difference as well as latency/ops overhead | 08 | PASS | `docs/benchmarks/COMPARISON.md`. Anchor confirmation is **one sample** |
| SEC-01 | Secret scan and .gitignore scan | no private keys or corp/real-bank data in Git | 09 | PASS | `docs/publication/secret-scan.txt`: 148-file publish set, no PEM key, no token patterns, no sensitive file types, only Anvil's two public dev keys in the fixture. Pattern scan only. No dedicated scanner was run and there is no git history yet |
| PUB-01 | Clean clone on ARM64 with setup guide | reproducible end-to-end local walkthrough | 09 | NOT EXECUTED | Needs the maintainer's approval to create a temporary checkout. Individual make targets ran in place, which does not prove a clean clone works. The CI install path (`requirements.lock`) is also unverified |
| PUB-02 | Honest publish statement | declares local Anvil != permissioned QBFT consensus, synthetic results != bank production | 09 | PASS | `README.md` (opening and "Scope and limitations"), `docs/publication/RELEASE_NOTES.md`, `docs/publication/linkedin-followup.md`, `SECURITY.md` |

## Summary

32 PASS, 0 FAIL, 2 NOT EXECUTED (UI-02, PUB-01). Several PASS rows carry a stated limit in the notes. Those limits are real and should be read, particularly ENV-02, EVD-04, UI-01, and SEC-01.

Not covered by this table: the GitHub Actions workflow has never run on GitHub, and the ≥85% coverage target below was not measured because no coverage tool is installed.

## Suggested demo criteria

1. Fraud-ring sample shows linked simulated bank accounts and a REVIEW/HIGH decision with feature-backed reasons.
2. API responds promptly without synchronously waiting for chain confirmation.
3. Canonical signed receipt passes independent CLI check against pinned issuer public key and on-chain digest.
4. Modified decision field fails independently, not because UI makes a claim.
5. Ledger RPC outage does not prevent off-chain scoring; worker later recovers without duplicate commitments.
6. Benchmark report generated from actual executed tests and includes the comparison to a signed local audit log.

## Quality policy

Aim for ≥85% coverage on critical receipt + verifier modules and meaningful tests on contract and outbox. A numerical coverage percentage does **not** substitute for testing failure paths and cryptographic edge cases. All published metrics must be reproducible and clearly labeled experimental synthetic data.
