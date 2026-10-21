"""Unit tests for on-chain replay and ingestion synchronization.

Verifies ONC-01, ONC-02, ONC-04, ONC-05, and ONC-06 offline using mock RPC clients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from veritas.ledger.client import ChainResetError, LedgerConfig
from veritas.onchain.abi import (
    ACCOUNT_REGISTERED_TOPIC,
    TRANSFER_RECORDED_TOPIC,
    to_bytes32,
    to_uint256,
)
from veritas.onchain.client import (
    PINNED_TRANSFER_LOG_RUNTIME_SHA256,
    TransferLogClient,
)
from veritas.onchain.ingest import ingest_events
from veritas.onchain.replay import replay_dataset
from veritas.simulator.store import seed_database
from veritas.storage.db import connect


class MockTransferLogClient(TransferLogClient):
    """In-memory mock for TransferLogClient to test replay and ingest logic."""

    def __init__(self, logs: list[dict[str, Any]] | None = None) -> None:
        self.config = LedgerConfig(
            rpc_url="http://127.0.0.1:8545",
            chain_id=31337,
            contract_address="0x5fbdb2315678afecb367f032d93f642f64180aa3",
            runtime_code_sha256=PINNED_TRANSFER_LOG_RUNTIME_SHA256,
        )
        super().__init__(self.config)
        self.registered_account_batches: list[dict[str, Any]] = []
        self.recorded_transfer_batches: list[dict[str, Any]] = []
        self.logs: list[dict[str, Any]] = logs or []
        self.blocks: dict[int, dict[str, Any]] = {
            0: {"hash": "0xgenesis0000000000000000000000000000000000000000000000000000000000"},
            1: {"hash": "0xblock100000000000000000000000000000000000000000000000000000000000"},
            2: {"hash": "0xblock200000000000000000000000000000000000000000000000000000000000"},
        }
        self.current_block = 2

    def validate(self) -> None:
        pass

    def get_block_number(self) -> int:
        return self.current_block

    def get_block_by_number(self, block_number: int | str, full_tx: bool = False) -> dict[str, Any]:
        num = int(block_number, 16) if isinstance(block_number, str) else int(block_number)
        if num in self.blocks:
            return self.blocks[num]
        return {"hash": f"0xblock{num:060d}"}

    def get_logs(
        self,
        from_block: int | str,
        to_block: int | str = "latest",
        topics: list[str | None] | None = None,
    ) -> list[dict[str, Any]]:
        return self.logs

    def send_register_accounts(
        self,
        from_address: str,
        account_ids: list[str],
        bank_ids: list[str],
        opened_ats: list[int],
        gas: str = "0x800000",
    ) -> str:
        self.registered_account_batches.append(
            {
                "from": from_address,
                "accounts": account_ids,
                "banks": bank_ids,
                "opened_ats": opened_ats,
            }
        )
        return f"0xacctx{len(self.registered_account_batches)}"

    def send_record_transfers(
        self,
        from_address: str,
        tx_ids: list[str],
        froms: list[str],
        tos: list[str],
        amounts_minor: list[int],
        event_times: list[int],
        gas: str = "0x800000",
    ) -> str:
        self.recorded_transfer_batches.append(
            {
                "from": from_address,
                "tx_ids": tx_ids,
                "froms": froms,
                "tos": tos,
                "amounts": amounts_minor,
                "event_times": event_times,
            }
        )
        return f"0xtxtx{len(self.recorded_transfer_batches)}"


def _build_test_logs() -> list[dict[str, Any]]:
    sender = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    logs = [
        # Account 1
        {
            "topics": [
                ACCOUNT_REGISTERED_TOPIC,
                "0x" + to_bytes32("acct-0001").hex(),
                "0x" + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex(),
            ],
            "data": (
                "0x"
                + to_bytes32("BANK_A").hex()
                + to_uint256(1768467600).hex()
                + to_uint256(1).hex()
            ),
            "blockNumber": "0x1",
            "transactionHash": "0xtxacc1",
            "logIndex": "0x0",
            "blockHash": "0x" + "1" * 64,
        },
        # Account 2
        {
            "topics": [
                ACCOUNT_REGISTERED_TOPIC,
                "0x" + to_bytes32("acct-0002").hex(),
                "0x" + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex(),
            ],
            "data": (
                "0x"
                + to_bytes32("BANK_B").hex()
                + to_uint256(1768467660).hex()
                + to_uint256(1).hex()
            ),
            "blockNumber": "0x1",
            "transactionHash": "0xtxacc2",
            "logIndex": "0x1",
            "blockHash": "0x" + "1" * 64,
        },
        # Transfer 1
        {
            "topics": [
                TRANSFER_RECORDED_TOPIC,
                "0x" + to_bytes32("txn-000001").hex(),
                "0x" + to_bytes32("acct-0001").hex(),
                "0x" + to_bytes32("acct-0002").hex(),
            ],
            "data": (
                "0x"
                + to_uint256(50000).hex()
                + to_uint256(1768467700).hex()
                + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex()
                + to_uint256(2).hex()
            ),
            "blockNumber": "0x2",
            "transactionHash": "0xtxtrf1",
            "logIndex": "0x0",
            "blockHash": "0xblock200000000000000000000000000000000000000000000000000000000000",
        },
    ]
    return logs


def test_replay_batches_and_omits_labels(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    seed_database(source_db, seed=42, scale="tiny", replace=False, confirm_benchmark=False)

    mock_client = MockTransferLogClient()
    stats = replay_dataset(
        source_db,
        mock_client,
        from_address="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        batch_size=50,
    )

    assert stats["accounts_replayed"] == 100
    assert stats["transfers_replayed"] == 500
    assert stats["account_tx_count"] == 2  # 100 accounts / 50 batch size
    assert stats["transfer_tx_count"] == 10  # 500 transfers / 50 batch size

    # Verify ONC-06: Calldata batches contain no scenario_id or label
    for batch in mock_client.recorded_transfer_batches:
        assert "scenario_id" not in batch
        assert "label" not in batch
        assert len(batch["tx_ids"]) <= 50


def test_ingest_records_events_and_provenance(tmp_path: Path) -> None:
    target_db = tmp_path / "target.db"
    mock_client = MockTransferLogClient(logs=_build_test_logs())

    result = ingest_events(target_db, mock_client)
    assert result["accounts_ingested"] == 2
    assert result["transfers_ingested"] == 1

    with connect(target_db) as conn:
        accs = conn.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        assert len(accs) == 2
        assert accs[0]["account_id"] == "acct-0001"
        assert accs[1]["account_id"] == "acct-0002"

        txs = conn.execute("SELECT * FROM transactions").fetchall()
        assert len(txs) == 1
        assert txs[0]["transaction_id"] == "txn-000001"
        assert txs[0]["scenario_id"] is None  # Labels and scenario_id absent

        refs = conn.execute("SELECT * FROM onchain_transfer_refs").fetchall()
        assert len(refs) == 1
        assert refs[0]["transaction_id"] == "txn-000001"
        assert refs[0]["chain_id"] == 31337
        assert refs[0]["block_number"] == 2
        assert refs[0]["tx_hash"] == "0xtxtrf1"
        assert refs[0]["log_index"] == 0

        cursor = conn.execute("SELECT * FROM onchain_cursor WHERE cursor_id = 1").fetchone()
        assert cursor is not None
        assert cursor["chain_id"] == 31337
        assert cursor["last_block_hash"] == (
            "0xblock200000000000000000000000000000000000000000000000000000000000"
        )


def test_ingest_atomicity_on_error(tmp_path: Path) -> None:
    """ONC-04: Error mid-ingest aborts transaction; cursor never ahead of committed rows."""
    target_db = tmp_path / "target.db"
    bad_logs = _build_test_logs()
    # Add a malformed log that fails decoding
    bad_logs.append(
        {
            "topics": [TRANSFER_RECORDED_TOPIC],
            "data": "0x12",
            "blockNumber": "0x3",
            "transactionHash": "0xerr",
            "logIndex": "0x0",
        }
    )

    mock_client = MockTransferLogClient(logs=bad_logs)
    mock_client.current_block = 3
    mock_client.blocks[3] = {"hash": "0x" + "3" * 64}

    with pytest.raises(ValueError):
        ingest_events(target_db, mock_client)

    # Database must have 0 rows and NO cursor committed
    with connect(target_db) as conn:
        cursor = conn.execute("SELECT * FROM onchain_cursor WHERE cursor_id = 1").fetchone()
        assert cursor is None
        acc_count = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
        assert acc_count == 0


def test_chain_reset_detection(tmp_path: Path) -> None:
    """ONC-05: Chain reset produces explicit error. Rows untouched unless --rebuild."""
    target_db = tmp_path / "target.db"
    mock_client = MockTransferLogClient(logs=_build_test_logs())
    ingest_events(target_db, mock_client)

    # Simulate chain reset: block 2 has different hash now
    mock_client.blocks[2] = {"hash": "0x" + "f" * 64}

    with pytest.raises(ChainResetError, match="Chain reset detected"):
        ingest_events(target_db, mock_client)

    # Existing rows remain untouched
    with connect(target_db) as conn:
        acc_count = conn.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"]
        assert acc_count == 2

    # With rebuild=True, rows are wiped and re-ingested
    mock_client.blocks[2] = {
        "hash": "0xblock200000000000000000000000000000000000000000000000000000000000"
    }
    rebuild_stats = ingest_events(target_db, mock_client, rebuild=True)
    assert rebuild_stats["accounts_ingested"] == 2
    assert rebuild_stats["transfers_ingested"] == 1


def test_end_to_end_sync_and_scoring_parity(tmp_path: Path) -> None:
    """ONC-02, ONC-03, ONC-07: Fingerprint equality, scoring parity, and provenance ref."""
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "target.db"
    seed_database(source_db, seed=42, scale="tiny", replace=False, confirm_benchmark=False)

    sender = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    mock_client = MockTransferLogClient()

    # Replay from source
    replay_stats = replay_dataset(
        source_db,
        mock_client,
        from_address=sender,
        batch_size=50,
    )
    assert replay_stats["accounts_replayed"] == 100
    assert replay_stats["transfers_replayed"] == 500

    # Build simulated event logs from recorded batches
    generated_logs: list[dict[str, Any]] = []
    block_num = 1
    log_idx = 0

    for batch in mock_client.registered_account_batches:
        for acc_id, bank_id, opened_at in zip(
            batch["accounts"], batch["banks"], batch["opened_ats"], strict=True
        ):
            generated_logs.append(
                {
                    "topics": [
                        ACCOUNT_REGISTERED_TOPIC,
                        "0x" + to_bytes32(acc_id).hex(),
                        "0x" + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex(),
                    ],
                    "data": (
                        "0x"
                        + to_bytes32(bank_id).hex()
                        + to_uint256(opened_at).hex()
                        + to_uint256(block_num).hex()
                    ),
                    "blockNumber": hex(block_num),
                    "transactionHash": "0x" + "a" * 64,
                    "logIndex": hex(log_idx),
                    "blockHash": "0x" + "b" * 64,
                }
            )
            log_idx += 1
        block_num += 1

    for batch in mock_client.recorded_transfer_batches:
        for tx_id, f_acc, t_acc, amt, evt_time in zip(
            batch["tx_ids"],
            batch["froms"],
            batch["tos"],
            batch["amounts"],
            batch["event_times"],
            strict=True,
        ):
            generated_logs.append(
                {
                    "topics": [
                        TRANSFER_RECORDED_TOPIC,
                        "0x" + to_bytes32(tx_id).hex(),
                        "0x" + to_bytes32(f_acc).hex(),
                        "0x" + to_bytes32(t_acc).hex(),
                    ],
                    "data": (
                        "0x"
                        + to_uint256(amt).hex()
                        + to_uint256(evt_time).hex()
                        + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex()
                        + to_uint256(block_num).hex()
                    ),
                    "blockNumber": hex(block_num),
                    "transactionHash": "0x" + "c" * 64,
                    "logIndex": hex(log_idx),
                    "blockHash": "0x" + "d" * 64,
                }
            )
            log_idx += 1
        block_num += 1

    mock_client.logs = generated_logs
    mock_client.current_block = block_num
    mock_client.blocks[block_num] = {"hash": "0x" + "d" * 64}

    # Ingest into fresh target_db
    ingest_stats = ingest_events(target_db, mock_client)
    assert ingest_stats["accounts_ingested"] == 100
    assert ingest_stats["transfers_ingested"] == 500

    # ONC-02: Fingerprint of (id, from, to, amount, time) equals off-chain seed-42
    with connect(source_db) as src_conn, connect(target_db) as tgt_conn:
        src_rows = src_conn.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time
            FROM transactions ORDER BY transaction_id
            """
        ).fetchall()
        tgt_rows = tgt_conn.execute(
            """
            SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time
            FROM transactions ORDER BY transaction_id
            """
        ).fetchall()
        assert len(src_rows) == len(tgt_rows) == 500
        for s, t in zip(src_rows, tgt_rows, strict=True):
            assert tuple(s) == tuple(t)

        # Labels and scenario_id are absent in target_db
        scen_count = tgt_conn.execute(
            "SELECT COUNT(*) AS c FROM transactions WHERE scenario_id IS NOT NULL"
        ).fetchone()["c"]
        assert scen_count == 0

    # ONC-03: Score sampled transactions from both DBs, including txn-000007
    from veritas.decisions.service import evaluate_transaction, get_receipt
    from veritas.evidence.keys import ensure_signing_key

    key_path = tmp_path / "test_signer.pem"
    ensure_signing_key(key_path, "test-signer-1")

    for sample_id in ["txn-000007", "txn-000001", "txn-000050"]:
        dec_src = evaluate_transaction(
            source_db,
            transaction_id=sample_id,
            idempotency_key=f"idemp-src-{sample_id}",
            signing_key_path=key_path,
            signing_key_id="test-signer-1",
        )
        dec_tgt = evaluate_transaction(
            target_db,
            transaction_id=sample_id,
            idempotency_key=f"idemp-tgt-{sample_id}",
            signing_key_path=key_path,
            signing_key_id="test-signer-1",
        )

        assert dec_src["decision"] == dec_tgt["decision"]
        assert dec_src["risk_score"] == dec_tgt["risk_score"]
        assert dec_src["reason_codes"] == dec_tgt["reason_codes"]
        assert dec_src["feature_snapshot_sha256"] == dec_tgt["feature_snapshot_sha256"]

        # ONC-07: Ingested transfer carries provenance ref matching onchain data
        assert dec_tgt["source_ref"] is not None
        assert dec_tgt["source_ref"]["chain_id"] == 31337
        assert dec_tgt["source_ref"]["tx_hash"] == "0x" + "c" * 64

        receipt_tgt = get_receipt(target_db, dec_tgt["decision_id"])
        assert receipt_tgt is not None
        assert receipt_tgt["payload"]["source_ref"]["chain_id"] == 31337
        assert receipt_tgt["payload"]["source_ref"]["tx_hash"] == "0x" + "c" * 64

        # Source DB without onchain refs has no source_ref
        assert dec_src["source_ref"] is None
