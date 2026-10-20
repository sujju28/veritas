# Decision evidence protocol 1.0

The signed payload uses `schema_version` `1.0`. The ruleset is `rules-v1`. The optional anomaly model is `iforest-v1`. The local chain id is `31337`.

## Payload

The canonical payload contains `schema_version`, `decision_id`, `transaction_id`, `bank_id`, `decision`, `risk_score`, sorted unique `reason_codes`, `feature_snapshot_sha256`, `model_version`, `ruleset_version`, and `decision_timestamp`. Strings are NFC-normalized. Bytes are RFC 8785 canonical JSON. The digest is SHA-256 of those bytes. Ed25519 signs those same bytes. The receipt wrapper adds `digest_hex`, `signature_b64`, `signing_key_id`, and `signature_algorithm`. It does not contain the issuer public key.

## Trust

The pinned public keys live in `trust-registry.json` beside the gitignored private key. Verification rejects a receipt whose digest does not match the canonical payload (`TAMPERED`), whose key id is absent (`UNKNOWN_ISSUER`), or whose signature does not verify (`INVALID_SIGNATURE`). A valid signature with no reachable chain is `VERIFICATION_UNAVAILABLE` or, before the chain call, `SIGNATURE_VALID_OFFLINE`. `VERIFIED_ONCHAIN` requires the digest, the signature, the chain id, the contract address, the runtime bytecode hash, and a matching on-chain commitment.

## Chain commitment

`decision_key` is SHA-256 of the ASCII prefix `VERITAS:DECISION:` plus the decision id. The contract stores that key and the evidence digest. It does not store account ids, amounts, or the receipt. The pinned runtime SHA-256 is `9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db`.

The OpenAPI document generated from the FastAPI application is `docs/openapi.json`.

## Verifier status taxonomy (protocol 1.0)

`python -m veritas.verifier verify` exits `0` only for `VERIFIED_ONCHAIN`. Every other status exits `1`. Statuses are produced by `backend/veritas/evidence/verify.py` (offline) and `backend/veritas/verifier/check.py` (chain).

| Status | Meaning |
|---|---|
| `MALFORMED` | The receipt is missing mandatory fields or has the wrong shape |
| `TAMPERED` | The digest recomputed from the canonical payload differs from `digest_hex` |
| `UNKNOWN_ISSUER` | `signing_key_id` is not in the pinned trust registry |
| `INVALID_SIGNATURE` | The Ed25519 signature does not verify under the pinned key |
| `SIGNATURE_VALID_OFFLINE` | Digest and signature are valid. No chain check was made (offline only) |
| `VERIFICATION_UNAVAILABLE` | The RPC call failed. This is never reported as verified |
| `CONFIG_MISMATCH` | Chain id, contract address, or runtime bytecode hash does not match the pinned values, or the address has no code (for example a reset chain) |
| `PENDING_ANCHOR` | Receipt is valid and the chain has no commitment for the decision key yet |
| `ONCHAIN_MISMATCH` | The chain holds a different digest for the decision key |
| `VERIFIED_ONCHAIN` | Digest, signature, chain id, contract address, runtime hash, and on-chain digest all match |

A live example of `VERIFIED_ONCHAIN`, `TAMPERED`, `CONFIG_MISMATCH`, and `VERIFICATION_UNAVAILABLE` on one receipt is `docs/publication/tamper-cli-live.txt`.

## Version policy

`schema_version` is `1.0`. A change to the payload fields, the canonicalization, the signed bytes, or the decision-key derivation requires a new `schema_version`, and the verifier must reject versions it does not know. Today `EvidencePayload.schema_version` is constrained to the pattern `^1\.0$` in `backend/veritas/evidence/models.py`, so any other value is reported as `MALFORMED`. Receipts that carry `1.0` stay verifiable against the pinned `DecisionRegistry` runtime hash. A new contract build changes that hash and needs a new pinned value and a new deployment. Neither is a migration of old on-chain commitments.

## Contract identity

| Item | Value |
|---|---|
| Chain id | `31337` (local Anvil) |
| Contract | `DecisionRegistry`, solc 0.8.28, EVM `cancun`, optimizer 200 runs |
| Foundry | 1.8.5 |
| Runtime bytecode | 1,273 bytes |
| Runtime SHA-256 | `9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db` |
| Source of the pin | `contracts/fixtures/DecisionRegistry.build.json`, checked by `contracts/script/deploy-local.sh` and by the verifier |

Recompute the checksum against a running Anvil with the deployed address:

```bash
cast code <address> --rpc-url http://127.0.0.1:8545 \
  | python3 -c 'import hashlib,sys; print(hashlib.sha256(bytes.fromhex(sys.stdin.read().strip().removeprefix("0x"))).hexdigest())'
```

The address `0x5FbDB2315678afecb367f032d93F642f64180aa3` is the deterministic result of the first deployment from Anvil's first sample account on a fresh chain. It is not a secret and it is not unique to this project.
