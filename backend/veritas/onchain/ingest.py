"""Ingest events from the TransferLog contract into a local SQLite database.

Guarantees atomicity: all rows and the onchain cursor are committed in a
single transaction. Performs chain continuity checks to detect resets (ONC-05).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from veritas.ledger.client import ChainResetError, LedgerConfig
from veritas.onchain.abi import (
    ACCOUNT_REGISTERED_TOPIC,
    TRANSFER_RECORDED_TOPIC,
    decode_account_registered_log,
    decode_transfer_recorded_log,
    unix_to_iso,
)
from veritas.onchain.client import (
    PINNED_TRANSFER_LOG_RUNTIME_SHA256,
    TransferLogClient,
)
from veritas.storage.db import apply_migrations, connect, transaction


def ingest_events(
    target_db: Path,
    client: TransferLogClient,
    *,
    rebuild: bool = False,
) -> dict[str, Any]:
    """Sync events from TransferLog into target_db, tracking block cursor atomically."""
    client.validate()
    apply_migrations_to_db(target_db)

    latest_block = client.get_block_number()

    with connect(target_db) as conn:
        if rebuild:
            with transaction(conn):
                conn.execute("DELETE FROM onchain_cursor")
                conn.execute("DELETE FROM onchain_transfer_refs")
                conn.execute("DELETE FROM decisions")
                conn.execute("DELETE FROM feature_snapshots")
                conn.execute("DELETE FROM evidence_receipts")
                conn.execute("DELETE FROM anchor_outbox")
                conn.execute("DELETE FROM transactions")
                conn.execute("DELETE FROM accounts")
                conn.execute("DELETE FROM banks")

        cursor_row = conn.execute(
            """
            SELECT chain_id, contract_address, last_block_number, last_block_hash
            FROM onchain_cursor WHERE cursor_id = 1
            """
        ).fetchone()

        if cursor_row is not None:
            last_chain_id = int(cursor_row["chain_id"])
            last_addr = cursor_row["contract_address"]
            last_block_num = int(cursor_row["last_block_number"])
            last_block_hash = cursor_row["last_block_hash"]

            if last_chain_id != client._config.chain_id:
                raise ChainResetError(
                    f"Chain ID changed from {last_chain_id} to {client._config.chain_id}. "
                    "Use --rebuild to reset state."
                )
            if last_addr.lower() != client._address.lower():
                raise ChainResetError(
                    f"Contract address changed from {last_addr} to {client._address}. "
                    "Use --rebuild to reset state."
                )

            # Continuity check: check that last_block_hash matches block on chain
            if last_block_num <= latest_block:
                try:
                    block_data = client.get_block_by_number(last_block_num)
                    observed_hash = block_data.get("hash")
                    if observed_hash and observed_hash.lower() != last_block_hash.lower():
                        raise ChainResetError(
                            f"Chain reset detected: block {last_block_num} hash {last_block_hash} "
                            f"does not match chain block hash {observed_hash}. "
                            "Existing rows untouched. Run with --rebuild to re-ingest."
                        )
                except Exception as exc:
                    if isinstance(exc, ChainResetError):
                        raise
                    raise ChainResetError(
                        f"Failed to verify chain continuity at block {last_block_num}: {exc}. "
                        "Run with --rebuild to re-ingest."
                    ) from exc
            else:
                raise ChainResetError(
                    f"Cursor block {last_block_num} is ahead of latest chain block {latest_block}. "
                    "Run with --rebuild to re-ingest."
                )

            from_block = last_block_num + 1
        else:
            from_block = 0

        if from_block > latest_block:
            return {
                "from_block": from_block,
                "latest_block": latest_block,
                "accounts_ingested": 0,
                "transfers_ingested": 0,
                "logs_processed": 0,
            }

        logs = client.get_logs(from_block, latest_block)

        def _log_key(log_item: dict[str, Any]) -> tuple[int, int]:
            bn = log_item.get("blockNumber", 0)
            b_int = int(bn, 16) if isinstance(bn, str) else int(bn)
            li = log_item.get("logIndex", 0)
            l_int = int(li, 16) if isinstance(li, str) else int(li)
            return (b_int, l_int)

        logs.sort(key=_log_key)

        accounts_ingested = 0
        transfers_ingested = 0
        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Atomic commit: all data rows and cursor updated in one transaction
        with transaction(conn):
            for log in logs:
                topics = log.get("topics", [])
                if not topics:
                    continue
                topic0 = topics[0].lower()

                if topic0 == ACCOUNT_REGISTERED_TOPIC.lower():
                    decoded_acc = decode_account_registered_log(log)
                    bank_id = decoded_acc["bank_id"]
                    opened_at_iso = unix_to_iso(decoded_acc["opened_at"])

                    conn.execute(
                        "INSERT OR IGNORE INTO banks (bank_id, display_name) VALUES (?, ?)",
                        (bank_id, bank_id),
                    )
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO accounts (account_id, bank_id, opened_at)
                        VALUES (?, ?, ?)
                        """,
                        (decoded_acc["account_id"], bank_id, opened_at_iso),
                    )
                    accounts_ingested += 1

                elif topic0 == TRANSFER_RECORDED_TOPIC.lower():
                    decoded_tx = decode_transfer_recorded_log(log)
                    event_time_iso = unix_to_iso(decoded_tx["event_time"])

                    conn.execute(
                        """
                        INSERT OR IGNORE INTO transactions
                        (transaction_id, from_account_id, to_account_id, amount_minor,
                         event_time, currency, scenario_id)
                        VALUES (?, ?, ?, ?, ?, 'USD', NULL)
                        """,
                        (
                            decoded_tx["transaction_id"],
                            decoded_tx["from_account_id"],
                            decoded_tx["to_account_id"],
                            decoded_tx["amount_minor"],
                            event_time_iso,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO onchain_transfer_refs
                        (transaction_id, chain_id, block_number, block_hash, tx_hash,
                         log_index, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decoded_tx["transaction_id"],
                            client._config.chain_id,
                            decoded_tx["block_number"],
                            decoded_tx["block_hash"],
                            decoded_tx["tx_hash"],
                            decoded_tx["log_index"],
                            now_iso,
                        ),
                    )
                    transfers_ingested += 1

            # Update cursor to latest_block
            latest_block_data = client.get_block_by_number(latest_block)
            latest_hash = latest_block_data.get("hash", "0x" + "0" * 64)

            conn.execute(
                """
                INSERT OR REPLACE INTO onchain_cursor
                (cursor_id, chain_id, contract_address, last_block_number,
                 last_block_hash, updated_at)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                (
                    client._config.chain_id,
                    client._address,
                    latest_block,
                    latest_hash,
                    now_iso,
                ),
            )

    return {
        "from_block": from_block,
        "latest_block": latest_block,
        "accounts_ingested": accounts_ingested,
        "transfers_ingested": transfers_ingested,
        "logs_processed": len(logs),
    }


def apply_migrations_to_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        apply_migrations(conn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m veritas.onchain.ingest")
    parser.add_argument("--db", type=Path, required=True, help="Path to target SQLite db")
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545", help="Anvil RPC URL")
    parser.add_argument("--chain-id", type=int, default=31337, help="Anvil chain ID")
    parser.add_argument("--contract-address", required=True, help="TransferLog contract address")
    parser.add_argument(
        "--code-sha256",
        default=PINNED_TRANSFER_LOG_RUNTIME_SHA256,
        help="Pinned runtime code SHA256",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Wipe chain-sourced tables and re-ingest from block 0",
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
        stats = ingest_events(args.db, client, rebuild=args.rebuild)
        json.dump(stats, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0
    except Exception as exc:
        print(f"Ingest failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
