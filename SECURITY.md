# Security

VERITAS is a local research prototype. It is not a production fraud system and it does not accept real customer data.

## Reporting

Open a private security advisory on the repository after the maintainer has published it, or contact the maintainer directly. Do not file a public issue that includes a key, a database, or a receipt from a machine that has been used with anything other than the synthetic seed.

This repository does not contain employer systems, employer data, or an authorization to discuss an employer.

## What stays off the chain and out of Git

- Account and transaction rows stay in local SQLite. The contract stores a 32-byte decision key and a 32-byte evidence digest.
- The issuer private key is created at `.local/keys/issuer.pem` with mode `0600`. That directory is gitignored.
- `.env` and `.env.local` are gitignored. `.env.example` contains paths and loopback URLs only.
- `data/`, `*.db`, and `.anvil/` are gitignored.

## Known public test credential

`contracts/fixtures/anvil-public-dev.json` contains Anvil's published development accounts 0 and 1 (the second is used to test the unauthorized-writer revert). Foundry documents them as insecure defaults. They are not project secrets and must never be used on a network that holds value. The secret scan treats that file as the only allowed copy of those published test keys.

## Local chain

Anvil on `127.0.0.1:8545`, chain id `31337`, is a resettable development EVM. Deleting `.anvil/` removes its commitments. One operator controls that process. It is not a permissioned QBFT network and it is not evidence of cross-bank governance.
