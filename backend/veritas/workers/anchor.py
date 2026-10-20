"""Polling outbox worker. It submits from an unlocked local account and stores no key."""

from __future__ import annotations

import argparse
import random
import time
from pathlib import Path

from veritas.ledger.client import LedgerClient, LedgerConfig
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.storage.db import apply_migrations, connect
from veritas.workers.outbox import process_once

# Anvil's published account 0. Anvil unlocks it. This module does not contain its key.
PUBLIC_ANCHOR_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anchor pending VERITAS decisions on local Anvil")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--chain-id", type=int, default=31337)
    parser.add_argument("--contract-address", default="")
    parser.add_argument("--code-sha256", default=PINNED_RUNTIME_SHA256)
    parser.add_argument("--from-address", default=PUBLIC_ANCHOR_ADDRESS)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.poll_seconds < 0.2:
        parser.error("poll interval must be at least 0.2 seconds")
    contract = args.contract_address or _env_value(".env.local", "VERITAS_CONTRACT_ADDRESS")
    if not contract:
        parser.error("contract address is required")
    client = LedgerClient(
        LedgerConfig(
            rpc_url=args.rpc_url,
            chain_id=args.chain_id,
            contract_address=contract,
            runtime_code_sha256=args.code_sha256,
        )
    )
    rng = random.Random()
    while True:
        with connect(args.db) as connection:
            apply_migrations(connection)
            outcome = process_once(
                connection,
                client,
                from_address=args.from_address,
                rng=rng,
            )
        if outcome is not None:
            print(f"{outcome.decision_id} {outcome.status} {outcome.error_category or ''}".rstrip())
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


def _env_value(path: str, name: str) -> str:
    file = Path(path)
    if not file.is_file():
        return ""
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return value.strip()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
