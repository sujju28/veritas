"""Ingest a slice of IBM Transactions for Anti-Money Laundering (HI-Small) into VERITAS SQLite."""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import datetime
from pathlib import Path

from veritas.storage.db import apply_migrations, connect, transaction

ROOT = Path(__file__).resolve().parents[2]
SCRATCH_DIR = Path(
    "/Users/sujai/.gemini/antigravity-ide/brain/13e6f86e-32ab-42dc-a424-3eab93114d60/scratch"
)
SCRATCH_ZIP = SCRATCH_DIR / "HI-Small_Trans.csv.zip"
DEFAULT_TARGET_DB = ROOT / "data" / "veritas-ibm.db"


def ingest_ibm_aml(
    zip_path: Path = SCRATCH_ZIP,
    target_db: Path = DEFAULT_TARGET_DB,
    max_background: int = 1800,
) -> None:
    if not zip_path.exists():
        raise FileNotFoundError(f"Missing zip file at {zip_path}")

    print(f"Opening {zip_path}...")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    if target_db.exists():
        target_db.unlink()

    # Step 1: Scan and select the laundering cluster + realistic background traffic
    target_hub = "070_100428660"
    laundering_rows: list[tuple[int, list[str]]] = []
    connected_rows: list[tuple[int, list[str]]] = []
    background_rows: list[tuple[int, list[str]]] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open("HI-Small_Trans.csv") as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"))
            _ = next(reader)  # Header

            counterparties = set()
            for row_idx, row in enumerate(reader):
                from_key = f"{row[1]}_{row[2]}"
                to_key = f"{row[3]}_{row[4]}"
                is_laundering = row[-1] == "1"

                if from_key == to_key:
                    # Skip self-transfers (reinvestments)
                    continue

                if from_key == target_hub:
                    if is_laundering:
                        laundering_rows.append((row_idx, row))
                        counterparties.add(to_key)
                    elif len(connected_rows) < 50:
                        connected_rows.append((row_idx, row))
                elif to_key == target_hub and len(connected_rows) < 80:
                    connected_rows.append((row_idx, row))
                elif from_key in counterparties or to_key in counterparties:
                    if len(connected_rows) < 120:
                        connected_rows.append((row_idx, row))
                elif len(background_rows) < max_background:
                    background_rows.append((row_idx, row))

                stop_cond = len(background_rows) >= max_background and len(laundering_rows) >= 6
                if row_idx >= 300000 or stop_cond:
                    break

    selected_rows = laundering_rows + connected_rows + background_rows
    # Sort chronologically
    selected_rows.sort(key=lambda item: item[1][0])
    print(
        f"Selected {len(selected_rows)} transactions "
        f"(laundering: {len(laundering_rows)}, "
        f"connected: {len(connected_rows)}, "
        f"background: {len(background_rows)})"
    )

    # Step 2: Extract unique banks and accounts
    banks: dict[str, str] = {}
    accounts: dict[str, str] = {}
    tx_records: list[dict[str, object]] = []

    for _idx, (original_idx, row) in enumerate(selected_rows):
        time_raw = row[0]
        from_bank_raw = row[1]
        from_acc_raw = row[2]
        to_bank_raw = row[3]
        to_acc_raw = row[4]
        amt_raw = float(row[5])
        is_laundering = row[-1] == "1"

        from_bank_id = f"bank-{from_bank_raw}"
        to_bank_id = f"bank-{to_bank_raw}"
        banks[from_bank_id] = f"IBM AML Bank {from_bank_raw}"
        banks[to_bank_id] = f"IBM AML Bank {to_bank_raw}"

        from_acc_id = f"acc-{from_bank_raw}-{from_acc_raw}"
        to_acc_id = f"acc-{to_bank_raw}-{to_acc_raw}"
        accounts[from_acc_id] = from_bank_id
        accounts[to_acc_id] = to_bank_id

        # Skip self-transfers
        if from_acc_id == to_acc_id:
            continue

        dt = datetime.strptime(time_raw, "%Y/%m/%d %H:%M")
        iso_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        amt_minor = max(1, int(round(amt_raw * 100)))
        tx_id = f"txn-ibm-{original_idx:06d}"
        scenario_id = "ibm_aml_fanout" if is_laundering else None

        tx_records.append(
            {
                "transaction_id": tx_id,
                "from_account_id": from_acc_id,
                "to_account_id": to_acc_id,
                "amount_minor": amt_minor,
                "event_time": iso_time,
                "currency": "USD",
                "scenario_id": scenario_id,
                "is_laundering": is_laundering,
                "format": row[9],
            }
        )

    print(
        f"Processed {len(banks)} banks, {len(accounts)} accounts, "
        f"and {len(tx_records)} valid non-self transfers."
    )

    # Step 3: Populate SQLite
    hasher = hashlib.sha256()
    with connect(target_db) as conn:
        apply_migrations(conn)
        with transaction(conn):
            # Insert banks
            for b_id, d_name in sorted(banks.items()):
                conn.execute(
                    "INSERT INTO banks (bank_id, display_name) VALUES (?, ?)",
                    (b_id, d_name),
                )

            # Insert accounts
            for a_id, b_id in sorted(accounts.items()):
                conn.execute(
                    "INSERT INTO accounts (account_id, bank_id, opened_at) VALUES (?, ?, ?)",
                    (a_id, b_id, "2022-08-01T00:00:00Z"),
                )

            # Insert transactions
            for tx in tx_records:
                conn.execute(
                    """
                    INSERT INTO transactions (
                        transaction_id, from_account_id, to_account_id,
                        amount_minor, event_time, currency, scenario_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tx["transaction_id"],
                        tx["from_account_id"],
                        tx["to_account_id"],
                        tx["amount_minor"],
                        tx["event_time"],
                        tx["currency"],
                        tx["scenario_id"],
                    ),
                )
                line = (
                    f"{tx['transaction_id']},{tx['from_account_id']},"
                    f"{tx['to_account_id']},{tx['amount_minor']},{tx['event_time']}\n"
                )
                hasher.update(line.encode("utf-8"))

                if tx["is_laundering"]:
                    conn.execute(
                        """
                        INSERT INTO scenario_ground_truth (
                            ground_truth_id, scenario_id, transaction_id, account_id, label
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            f"gt-{tx['transaction_id']}",
                            "ibm_aml_fanout",
                            tx["transaction_id"],
                            tx["from_account_id"],
                            "LABEL_FRAUD",
                        ),
                    )

            content_sha256 = hasher.hexdigest()
            conn.execute(
                """
                INSERT INTO dataset_manifest (
                    manifest_id, seed, scale, account_count, transaction_count,
                    content_sha256, created_at
                ) VALUES (1, 42, 'ibm_aml_hi_small', ?, ?, ?, ?)
                """,
                (len(accounts), len(tx_records), content_sha256, "2022-09-01T00:00:00Z"),
            )

    print(f"Successfully populated {target_db}!")
    print(f"Content SHA-256: {content_sha256}")


if __name__ == "__main__":
    ingest_ibm_aml()
