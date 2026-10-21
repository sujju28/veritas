"""Typed JSON-RPC client for the TransferLog contract.

Zero external dependencies. Uses the same LedgerConfig, loopback checks,
and validation patterns as LedgerClient and RulesetClient.
"""

from __future__ import annotations

import hashlib
from typing import Any

from veritas.ledger.client import (
    ChainConfigError,
    ChainResetError,
    ChainRpcError,
    LedgerClient,
    _address,
)
from veritas.onchain.abi import (
    encode_record_transfers,
    encode_register_accounts,
)

PINNED_TRANSFER_LOG_RUNTIME_SHA256 = (
    "4a41fe0b568d01924f4effa8de9be0be57170ae660c928a9bdaf0b8b36aa4c3d"
)

IS_WRITER_SELECTOR = "0xb51ffb0a"


class TransferLogClient(LedgerClient):
    """Client for querying and recording to the on-chain TransferLog."""

    def validate(self) -> None:
        """Confirm chain id and that the pinned TransferLog runtime code is deployed."""
        observed = int(self._rpc("eth_chainId", []), 16)
        if observed != self._config.chain_id:
            raise ChainConfigError(
                f"RPC chain id {observed} does not match configured {self._config.chain_id}"
            )
        code = self._rpc("eth_getCode", [self._address, "latest"])
        if not isinstance(code, str) or code in {"0x", "0x0"}:
            raise ChainResetError("configured transfer log has no code at this address")
        digest = hashlib.sha256(bytes.fromhex(code.removeprefix("0x"))).hexdigest()
        if digest != self._config.runtime_code_sha256:
            raise ChainConfigError("deployed bytecode does not match the pinned transfer log build")

    def get_block_number(self) -> int:
        res = self._rpc("eth_blockNumber", [])
        if not isinstance(res, str) or not res.startswith("0x"):
            raise ChainRpcError("eth_blockNumber returned invalid response")
        return int(res, 16)

    def get_block_by_number(self, block_number: int | str, full_tx: bool = False) -> dict[str, Any]:
        num_arg = hex(block_number) if isinstance(block_number, int) else block_number
        res = self._rpc("eth_getBlockByNumber", [num_arg, full_tx])
        if not isinstance(res, dict):
            raise ChainRpcError(f"eth_getBlockByNumber for {block_number} returned no block")
        return res

    def get_logs(
        self,
        from_block: int | str,
        to_block: int | str = "latest",
        topics: list[str | None] | None = None,
    ) -> list[dict[str, Any]]:
        self.validate()
        filter_params: dict[str, Any] = {
            "address": self._address,
            "fromBlock": hex(from_block) if isinstance(from_block, int) else from_block,
            "toBlock": hex(to_block) if isinstance(to_block, int) else to_block,
        }
        if topics is not None:
            filter_params["topics"] = topics
        res = self._rpc("eth_getLogs", [filter_params])
        if not isinstance(res, list):
            raise ChainRpcError("eth_getLogs returned invalid response")
        return res

    def is_writer(self, address: str) -> bool:
        self.validate()
        addr_clean = _address(address)[2:].rjust(64, "0")
        call_data = IS_WRITER_SELECTOR + addr_clean
        res = self._rpc("eth_call", [{"to": self._address, "data": call_data}, "latest"])
        if not isinstance(res, str) or not res.startswith("0x"):
            raise ChainRpcError("isWriter call returned no payload")
        return int(res, 16) == 1

    def send_register_accounts(
        self,
        from_address: str,
        account_ids: list[str],
        bank_ids: list[str],
        opened_ats: list[int],
        gas: str = "0x800000",
    ) -> str:
        self.validate()
        calldata = encode_register_accounts(account_ids, bank_ids, opened_ats)
        submitted = self._rpc(
            "eth_sendTransaction",
            [
                {
                    "from": _address(from_address),
                    "to": self._address,
                    "data": calldata,
                    "gas": gas,
                }
            ],
        )
        if not isinstance(submitted, str) or not submitted.startswith("0x"):
            raise ChainRpcError("send_register_accounts did not return a transaction hash")
        return submitted

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
        self.validate()
        calldata = encode_record_transfers(tx_ids, froms, tos, amounts_minor, event_times)
        submitted = self._rpc(
            "eth_sendTransaction",
            [
                {
                    "from": _address(from_address),
                    "to": self._address,
                    "data": calldata,
                    "gas": gas,
                }
            ],
        )
        if not isinstance(submitted, str) or not submitted.startswith("0x"):
            raise ChainRpcError("send_record_transfers did not return a transaction hash")
        return submitted
