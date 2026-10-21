"""Typed JSON-RPC reader and writer for the local Anvil RulesetRegistry.

This module validates that the chain-id and deployed bytecode match the
pinned RulesetRegistry build before calling or sending transactions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from veritas.ledger.client import (
    ChainConfigError,
    ChainIdentityError,
    ChainResetError,
    ChainRpcError,
    LedgerClient,
    LedgerConfig,
    _address,
)
from veritas.risk.manifest import ruleset_manifest_sha256

PINNED_RULESET_REGISTRY_RUNTIME_SHA256 = (
    "8fbbb76dcc547f0cbc6038baa5ce45d88c7ebe2115ea3f4bb9639932efca6ccf"
)

REGISTER_SELECTOR = "0x2f926732"
DEPRECATE_SELECTOR = "0xc1c3448c"
GET_RULESET_SELECTOR = "0x19fc27ec"


def ruleset_key(version: str) -> bytes:
    """Precomputed ruleset key: sha256("VERITAS:RULESET:" || version)."""
    return hashlib.sha256(f"VERITAS:RULESET:{version}".encode()).digest()


@dataclass(frozen=True)
class OnChainRuleset:
    exists: bool
    manifest_sha256: bytes
    deprecated: bool
    sender: str
    block_number: int
    timestamp: int


def register_calldata(key: bytes, manifest_sha256: bytes) -> str:
    if len(key) != 32 or len(manifest_sha256) != 32:
        raise ChainIdentityError("ruleset arguments must be 32 bytes")
    if key == bytes(32) or manifest_sha256 == bytes(32):
        raise ChainIdentityError("ruleset arguments must be nonzero")
    return REGISTER_SELECTOR + key.hex() + manifest_sha256.hex()


def deprecate_calldata(key: bytes) -> str:
    if len(key) != 32:
        raise ChainIdentityError("ruleset key must be 32 bytes")
    if key == bytes(32):
        raise ChainIdentityError("ruleset key must be nonzero")
    return DEPRECATE_SELECTOR + key.hex()


class RulesetClient(LedgerClient):
    def validate(self) -> None:
        """Confirm chain id and that the pinned RulesetRegistry runtime code is deployed."""
        observed = int(self._rpc("eth_chainId", []), 16)
        if observed != self._config.chain_id:
            raise ChainConfigError(
                f"RPC chain id {observed} does not match configured {self._config.chain_id}"
            )
        code = self._rpc("eth_getCode", [self._address, "latest"])
        if not isinstance(code, str) or code in {"0x", "0x0"}:
            raise ChainResetError("configured ruleset registry has no code at this address")
        digest = hashlib.sha256(bytes.fromhex(code.removeprefix("0x"))).hexdigest()
        if digest != self._config.runtime_code_sha256:
            raise ChainConfigError(
                "deployed bytecode does not match the pinned ruleset registry build"
            )

    def get_ruleset(self, key: bytes) -> OnChainRuleset:
        if len(key) != 32:
            raise ChainIdentityError("ruleset key must be 32 bytes")
        self.validate()
        data = GET_RULESET_SELECTOR + key.hex()
        raw = self._rpc("eth_call", [{"to": self._address, "data": data}, "latest"])
        if not isinstance(raw, str) or not raw.startswith("0x"):
            raise ChainRpcError("getRuleset returned no payload")
        blob = bytes.fromhex(raw.removeprefix("0x"))
        if len(blob) < 192:
            raise ChainRpcError("getRuleset payload is short")
        return OnChainRuleset(
            exists=int.from_bytes(blob[0:32], "big") == 1,
            manifest_sha256=blob[32:64],
            deprecated=int.from_bytes(blob[64:96], "big") == 1,
            sender="0x" + blob[108:128].hex(),
            block_number=int.from_bytes(blob[128:160], "big"),
            timestamp=int.from_bytes(blob[160:192], "big"),
        )

    def send_register(self, from_address: str, key: bytes, manifest_sha256: bytes) -> str:
        self.validate()
        submitted = self._rpc(
            "eth_sendTransaction",
            [
                {
                    "from": _address(from_address),
                    "to": self._address,
                    "data": register_calldata(key, manifest_sha256),
                    "gas": "0x30000",
                }
            ],
        )
        if not isinstance(submitted, str) or not submitted.startswith("0x"):
            raise ChainRpcError("register submission did not return a transaction hash")
        return submitted

    def send_deprecate(self, from_address: str, key: bytes) -> str:
        self.validate()
        submitted = self._rpc(
            "eth_sendTransaction",
            [
                {
                    "from": _address(from_address),
                    "to": self._address,
                    "data": deprecate_calldata(key),
                    "gas": "0x30000",
                }
            ],
        )
        if not isinstance(submitted, str) or not submitted.startswith("0x"):
            raise ChainRpcError("deprecate submission did not return a transaction hash")
        return submitted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m veritas.ledger.ruleset")
    subparsers = parser.add_subparsers(dest="command", required=True)

    reg_parser = subparsers.add_parser("register", help="Register a ruleset manifest on-chain")
    reg_parser.add_argument("--manifest", type=Path, required=True)
    reg_parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    reg_parser.add_argument("--chain-id", type=int, required=True)
    reg_parser.add_argument("--contract-address", required=True)
    reg_parser.add_argument(
        "--from-address",
        default="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        help="Admin address on local Anvil",
    )
    reg_parser.add_argument("--code-sha256", default=PINNED_RULESET_REGISTRY_RUNTIME_SHA256)

    get_parser = subparsers.add_parser("get", help="Query a ruleset from the registry")
    get_parser.add_argument("--version", required=True)
    get_parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    get_parser.add_argument("--chain-id", type=int, required=True)
    get_parser.add_argument("--contract-address", required=True)
    get_parser.add_argument("--code-sha256", default=PINNED_RULESET_REGISTRY_RUNTIME_SHA256)

    args = parser.parse_args(argv)
    client = RulesetClient(
        LedgerConfig(
            rpc_url=args.rpc_url,
            chain_id=args.chain_id,
            contract_address=args.contract_address,
            runtime_code_sha256=args.code_sha256,
        )
    )

    if args.command == "register":
        manifest_data = json.loads(args.manifest.read_text(encoding="utf-8"))
        version = manifest_data["ruleset_version"]
        digest_hex = ruleset_manifest_sha256(manifest_data)
        key = ruleset_key(version)
        digest_bytes = bytes.fromhex(digest_hex)

        current = client.get_ruleset(key)
        if current.exists:
            if current.manifest_sha256 == digest_bytes:
                print(f"Ruleset {version} already registered with digest {digest_hex}")
                return 0
            print(
                f"Conflict: Ruleset {version} registered with different digest "
                f"{current.manifest_sha256.hex()}",
                file=sys.stderr,
            )
            return 1

        tx_hash = client.send_register(args.from_address, key, digest_bytes)
        print(f"Registered ruleset {version} ({digest_hex}) tx {tx_hash}")
        return 0

    if args.command == "get":
        key = ruleset_key(args.version)
        current = client.get_ruleset(key)
        out = {
            "version": args.version,
            "key": "0x" + key.hex(),
            "exists": current.exists,
            "manifest_sha256": current.manifest_sha256.hex() if current.exists else None,
            "deprecated": current.deprecated,
            "sender": current.sender if current.exists else None,
            "block_number": current.block_number if current.exists else None,
            "timestamp": current.timestamp if current.exists else None,
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
