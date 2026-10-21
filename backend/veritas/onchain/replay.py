"""Replay simulator dataset from SQLite onto the TransferLog contract.

Reads accounts and transactions from SQLite (read-only) and submits batched
transactions to TransferLog. Never sends labels, scenario IDs, or scores.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from veritas.ledger.client import LedgerConfig
from veritas.onchain.abi import iso_to_unix
from veritas.onchain.client import (
    PINNED_TRANSFER_LOG_RUNTIME_SHA256,
    TransferLogClient,
)
from veritas.storage.db import connect


def replay_dataset(
    source_db: Path,
    client: TransferLogClient,
    from_address: str,
    *,
    batch_size: int = 100,
) -> dict[str, Any]:
    """Replay accounts and transactions from source_db to the TransferLog contract."""
    if not source_db.is_file():
        raise FileNotFoundError(f"Source database does not exist: {source_db}")

    with connect(source_db) as conn:
        account_rows = conn.execute(
            "SELECT account_id, bank_id, opened_at FROM accounts ORDER BY account_id"
        ).fetchall()
        tx_rows = conn.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time
            FROM transactions
            ORDER BY event_time, transaction_id
            """
        ).fetchall()

    if not account_rows or not tx_rows:
        raise ValueError(
            f"Source database at {source_db} has no accounts or transactions to replay"
        )

    account_txs: list[str] = []
    for i in range(0, len(account_rows), batch_size):
        batch = account_rows[i : i + batch_size]
        acc_ids = [row["account_id"] for row in batch]
        bank_ids = [row["bank_id"] for row in batch]
        opened_ats = [iso_to_unix(row["opened_at"]) for row in batch]
        tx_hash = client.send_register_accounts(from_address, acc_ids, bank_ids, opened_ats)
        account_txs.append(tx_hash)

    transfer_txs: list[str] = []
    for i in range(0, len(tx_rows), batch_size):
        batch = tx_rows[i : i + batch_size]
        tx_ids = [row["transaction_id"] for row in batch]
        froms = [row["from_account_id"] for row in batch]
        tos = [row["to_account_id"] for row in batch]
        amounts = [int(row["amount_minor"]) for row in batch]
        event_times = [iso_to_unix(row["event_time"]) for row in batch]
        tx_hash = client.send_record_transfers(
            from_address, tx_ids, froms, tos, amounts, event_times
        )
        transfer_txs.append(tx_hash)

    return {
        "accounts_replayed": len(account_rows),
        "transfers_replayed": len(tx_rows),
        "account_tx_count": len(account_txs),
        "transfer_tx_count": len(transfer_txs),
        "tx_hashes": account_txs + transfer_txs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m veritas.onchain.replay")
    parser.add_argument("--source-db", type=Path, required=True, help="Path to source SQLite db")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545", help="Anvil RPC URL")
    parser.add_argument("--chain-id", type=int, default=31337, help="Anvil chain ID")
    parser.add_argument("--contract-address", required=True, help="TransferLog contract address")
    parser.add_argument(
        "--from-address",
        default="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        help="Writer address with WRITE_ROLE",
    )
    parser.add_argument(
        "--code-sha256",
        default=PINNED_TRANSFER_LOG_RUNTIME_SHA256,
        help="Pinned runtime code SHA256",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for registration/recording",
    )

    args = parser.parse_args(argv)
    client = TransferLogClient(
        LedgerConfig(
            rpc_url=args.rpc_url,
            chain_id=args.chain_id,
            contract_address=args.contract_address,
            runtime_code_sha256=args.code_sha256,
        )
    )

    try:
        stats = replay_dataset(
            args.source_db,
            client,
            args.from_address,
            batch_size=args.batch_size,
        )
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"Replay failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
