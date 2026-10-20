# Trust and threat model

This model covers the local prototype. It does not cover a real bank network.

## Assets

- Synthetic transactions and the experimental score.
- The signed receipt and its issuer key.
- The SQLite outbox and the Anvil commitment.

## Trusted in this demo

- The operator of the laptop, because that person can read SQLite, hold the issuer key, and reset Anvil.
- The pinned issuer public key, for signature checks.
- The pinned contract bytecode hash, for chain identity checks.

## Not trusted

- The receipt file presented to the verifier. The verifier recomputes the digest and checks the signature against the pinned key.
- The scoring API, for verification. The CLI does not call it.
- Anvil, as a consortium. One operator controls it.

## What an attacker on this laptop can do

| Action | Detection |
|---|---|
| Change a signed field in a copied receipt | `TAMPERED` before any chain call |
| Replace the signature | `INVALID_SIGNATURE` |
| Present an unknown key id | `UNKNOWN_ISSUER` |
| Re-sign with the issuer private key | Not detected. The holder of that key is the issuer. |
| Edit SQLite and keep the old signature | The exported receipt fails the digest check |
| Reset Anvil | Empty code is a chain-identity failure, not a confirmation |
| Stop RPC | Decisions still return `anchor_status` `PENDING`. Verification stays `VERIFICATION_UNAVAILABLE` |

## Out of scope

Real payment authorization, customer data, multi-organization key custody, and a four-validator QBFT network.
