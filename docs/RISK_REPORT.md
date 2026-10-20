# Synthetic risk report

Generated from an executed rule-only scoring pass on the seed-42 tiny dataset (100 accounts, 500 transfers). The score is an experiment, not a probability.

| Item | Value |
|---|---|
| Dataset | synthetic seed 42 tiny |
| Scoring mode | `rule_only` |
| Ruleset | `rules-v1` |
| Labeled transfers | 12 |
| Flagged (`REVIEW` or `HIGH`) | 356 |
| True positive | 3 |
| False positive | 353 |
| False negative | 9 |
| Precision | 0.0084 |
| Recall | 0.25 |

A labeled transfer counts as positive even when it is only the start of a pattern. Three transfers reach a flag:

- `txn-000003` is `REVIEW` 65 with `FAN_IN` and `HIGH_VELOCITY` (BANK_A to BANK_B).
- `txn-000007` is `HIGH` 100 with `FAN_OUT`, `HIGH_VELOCITY`, and `RAPID_ONWARD` (BANK_B to BANK_C).
- `txn-000011` is `REVIEW` 55 with `MULTI_HOP` and `RAPID_ONWARD` (BANK_A to BANK_B).

The other nine labeled transfers are earlier hops. Their features have not crossed a 40-point band, so they stay `LOW`.

The 353 false positives come from the legitimate block: 488 transfers, one per second, across the remaining accounts. That whole block fits inside a 15-minute window, so many ordinary accounts also reach four counterparties or four transfers. These figures are not production bank-fraud accuracy.

Rules, each capped so the rule score stays in 0–100:

- `FAN_IN`: destination distinct predecessors in 15 minutes `>= 4` (40)
- `FAN_OUT`: source distinct successors in 15 minutes `>= 4` (40)
- `HIGH_VELOCITY`: source outbound count or destination inbound count in 15 minutes `>= 4` (25, once)
- `RAPID_ONWARD`: source onward amount ratio in 15 minutes `>= 0.8` (35)
- `MULTI_HOP`: upstream distance `>= 3` within four hops (20)

Bands are `LOW` 0–39, `REVIEW` 40–69, and `HIGH` 70–100. When a verified IsolationForest artifact is loaded, the experimental score is `(6 * normalized_anomaly + 4 * rule_score + 5) // 10`. Normalization uses the training decision-function 5th and 95th percentiles. The model is `iforest-v1`, trained once on a separate legitimate population with seed 7. It is not retrained per request.
