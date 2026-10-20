# ADR-001 — SQLite for the local prototype

## Status

Accepted for the M1 / 8 GB build.

## Decision

The prototype stores banks, accounts, transactions, decisions, receipts, and the anchor outbox in one SQLite file. The driver is the Python standard-library `sqlite3` module. Connections use WAL, foreign keys, and a busy timeout.

## Why

One file matches the memory budget. PostgreSQL would add another service. The decision, the signed receipt, and the outbox row are written in one SQLite transaction so a crash does not leave a score without its receipt.

## Consequence

SQLite is a local file. Anyone who can write that file can change rows. The signed receipt detects a change that is not re-signed. It does not provide a shared append-only log across operators.
