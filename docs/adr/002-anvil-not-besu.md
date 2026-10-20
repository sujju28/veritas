# ADR-002 — One native Anvil process, not Besu

## Status

Accepted for the M1 / 8 GB build.

## Decision

Chain anchoring uses one native Anvil 1.8.5 process on `127.0.0.1:8545`, chain id `31337`. The contract is `DecisionRegistry`. Four Besu validators are out of scope.

## Why

Four validator containers do not fit the memory budget and would look like a consortium. Anvil is a development EVM. One operator can stop it, replace `.anvil/state.json`, or redeploy the contract.

## Consequence

A commitment on this chain is an integrity check against a local process. It is not permissioned QBFT consensus and it does not show institutionally independent nodes. The pinned runtime bytecode SHA-256 is `9bef8ceb9b4888b3d31ab6c0e073cd34301145be187548e308e755a10f8978db` (1,273 bytes, solc 0.8.28, optimizer runs 200).
