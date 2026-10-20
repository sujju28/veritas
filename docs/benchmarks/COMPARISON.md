# Signed audit log and local Anvil commitment

Generated 2026-10-20T06:25:13Z. Seed 42.
Git revision `none`.
Host `macOS-26.6.2-arm64-arm-64bit-Mach-O` `arm64`, physical RAM 8589934592 bytes, Python 3.14.2.
Latency unit is milliseconds. RSS unit is bytes.
Percentiles use nearest-rank after 2 discarded warm-up calls. Scoring mode is `rule_only`.
These figures are one local run, not a bank production result.
With 15 samples, nearest-rank p95 and p99 can select the same observation.
Graph scoring reads the capped lookback window, so a 10k dataset
costs more to generate while one score stays near the default-window cost.

## What both approaches detect

A signed audit log stores the RFC 8785 payload, its SHA-256 digest,
and an Ed25519 signature under a pinned issuer key.
An on-chain commitment stores only the opaque decision-key digest
and that same evidence digest.
Changing a signed field changes the digest, so both the offline check
and a later chain comparison reject it.
Neither check detects a change that is re-signed by the issuer key holder.

## Trust and operations

| | Signed local audit log | Local Anvil commitment |
|---|---|---|
| Modification check | Canonical digest and Ed25519 | Same digest plus the chain digest |
| Trust | Issuer key and SQLite write access | Issuer key, bytecode, writer, operator |
| Processes | API process | API, Anvil, deploy, and worker |
| Failure | Decision stays anchor status PENDING | RPC loss queues a bounded retry |
| Measured default p50 | sign 0.050 ms, verify 0.112 ms, score 6.175 ms | anchor 60.161 ms (n=1) |

## What this local chain does not show

Anvil here is one resettable development chain on 127.0.0.1.
One operator can stop it, replace its state file, or redeploy the contract.
That is not a permissioned QBFT ledger.
It does not show a cross-bank governance advantage.
The extra cost is a second process, a writer role,
confirmation latency, and an outage path.
A commitment on this chain does not outrank the issuer key
when the same person controls both.
