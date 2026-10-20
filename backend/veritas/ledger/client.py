"""Typed JSON-RPC reader for the local Anvil DecisionRegistry.

This module does not submit transactions and does not start a worker.
A chain-id or bytecode mismatch is an identity failure, never a verified anchor.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

# First four bytes of keccak256(signature), from Foundry 1.8.5 `cast sig`.
GET_DECISION_SELECTOR = "0xd8c57892"
ANCHOR_SELECTOR = "0xc7e056bf"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ChainIdentityError(Exception):
    """The RPC endpoint is not the configured local chain or contract."""


class ChainConfigError(ChainIdentityError):
    """Chain id or bytecode does not match the pinned local registry."""


class ChainResetError(ChainIdentityError):
    """The configured address has no code. A reset chain is not a confirmation."""


class ChainRpcError(Exception):
    """The local RPC call failed. This is not an on-chain verification."""


class ContractRejected(ChainRpcError):
    """The registry reverted the anchor. This is not a confirmation."""


@dataclass(frozen=True)
class LedgerConfig:
    rpc_url: str
    chain_id: int
    contract_address: str
    runtime_code_sha256: str


@dataclass
class RpcRoute:
    """Choose a loopback RPC URL. Switching away does not delete Anvil state."""

    primary_url: str
    outage_url: str = "http://127.0.0.1:9"
    unavailable: bool = False

    def current_url(self) -> str:
        return self.outage_url if self.unavailable else self.primary_url


@dataclass(frozen=True)
class OnChainDecision:
    exists: bool
    evidence_digest: bytes
    sender: str
    block_number: int
    timestamp: int


class LedgerClient:
    def __init__(
        self,
        config: LedgerConfig,
        *,
        timeout_seconds: float = 2.0,
        route: RpcRoute | None = None,
    ) -> None:
        selected = route or RpcRoute(config.rpc_url)
        _require_loopback(selected.primary_url)
        _require_loopback(selected.outage_url)
        if config.chain_id <= 0:
            raise ChainIdentityError("chain id must be the local Anvil id")
        self._config = config
        self._timeout = timeout_seconds
        self._route = selected
        self._address = _address(config.contract_address)

    def validate(self) -> None:
        """Confirm chain id and that the pinned runtime code is deployed."""
        observed = int(self._rpc("eth_chainId", []), 16)
        if observed != self._config.chain_id:
            raise ChainConfigError(
                f"RPC chain id {observed} does not match configured {self._config.chain_id}"
            )
        code = self._rpc("eth_getCode", [self._address, "latest"])
        if not isinstance(code, str) or code in {"0x", "0x0"}:
            raise ChainResetError("configured contract has no code at this address")
        digest = hashlib.sha256(bytes.fromhex(code.removeprefix("0x"))).hexdigest()
        if digest != self._config.runtime_code_sha256:
            raise ChainConfigError("deployed bytecode does not match the pinned registry build")

    def get_decision(self, key: bytes) -> OnChainDecision:
        if len(key) != 32:
            raise ChainIdentityError("decision key must be 32 bytes")
        self.validate()
        data = GET_DECISION_SELECTOR + key.hex()
        raw = self._rpc("eth_call", [{"to": self._address, "data": data}, "latest"])
        if not isinstance(raw, str) or not raw.startswith("0x"):
            raise ChainRpcError("getDecision returned no payload")
        blob = bytes.fromhex(raw.removeprefix("0x"))
        if len(blob) < 160:
            raise ChainRpcError("getDecision payload is short")
        return OnChainDecision(
            exists=int.from_bytes(blob[0:32], "big") == 1,
            evidence_digest=blob[32:64],
            sender="0x" + blob[76:96].hex(),
            block_number=int.from_bytes(blob[96:128], "big"),
            timestamp=int.from_bytes(blob[128:160], "big"),
        )

    def send_anchor(self, from_address: str, key: bytes, evidence_digest: bytes) -> str:
        """Submit with an unlocked local account. The private key is not an argument."""
        self.validate()
        submitted = self._rpc(
            "eth_sendTransaction",
            [
                {
                    "from": _address(from_address),
                    "to": self._address,
                    "data": anchor_calldata(key, evidence_digest),
                    "gas": "0x30000",
                }
            ],
        )
        if not isinstance(submitted, str) or not submitted.startswith("0x"):
            raise ChainRpcError("anchor submission did not return a transaction hash")
        return submitted

    def transaction_receipt(self, tx_hash: str) -> dict[str, object] | None:
        if not tx_hash.startswith("0x"):
            raise ChainRpcError("transaction hash is missing")
        receipt = self._rpc("eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            return None
        if not isinstance(receipt, dict):
            raise ChainRpcError("transaction receipt was not an object")
        return receipt

    def _rpc(self, method: str, params: list[object]) -> object:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        request = urllib.request.Request(
            self._route.current_url(),
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ChainRpcError("local chain RPC is unavailable") from exc
        if not isinstance(payload, dict):
            raise ChainRpcError("local chain RPC returned an unexpected payload")
        if payload.get("error") is not None:
            message = json.dumps(payload["error"])
            if "revert" in message.lower():
                raise ContractRejected("the registry reverted the anchor")
            raise ChainRpcError("local chain RPC rejected the call")
        return payload.get("result")


def anchor_calldata(key: bytes, evidence_digest: bytes) -> str:
    """Unsigned calldata for a later worker. This function does not send a transaction."""
    if len(key) != 32 or len(evidence_digest) != 32:
        raise ChainIdentityError("anchor arguments must be 32 bytes")
    if key == bytes(32) or evidence_digest == bytes(32):
        raise ChainIdentityError("anchor arguments must be nonzero")
    return ANCHOR_SELECTOR + key.hex() + evidence_digest.hex()


def _require_loopback(rpc_url: str) -> None:
    parsed = urlparse(rpc_url)
    host = parsed.hostname
    if parsed.scheme != "http" or host not in LOOPBACK_HOSTS:
        raise ChainIdentityError("chain RPC must use http on a loopback host")


def _address(value: str) -> str:
    text = value.lower()
    if not text.startswith("0x") or len(text) != 42:
        raise ChainIdentityError("contract address must be a 20-byte hex value")
    try:
        int(text[2:], 16)
    except ValueError as exc:
        raise ChainIdentityError("contract address must be a 20-byte hex value") from exc
    return text
