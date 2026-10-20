"""Process settings. The bind host stays on the loopback interface."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    db_path: Path = Path("data/veritas.db")
    cors_origin: str = "http://127.0.0.1:5173"
    scoring_mode: str = "auto"
    model_path: Path | None = None
    signing_key_path: Path = Path(".local/keys/issuer.pem")
    signing_key_id: str = "issuer-local-1"
    chain_rpc_url: str = "http://127.0.0.1:8545"
    chain_id: int = 31337
    contract_address: str = ""

    @field_validator("host")
    @classmethod
    def host_must_be_loopback(cls, value: str) -> str:
        if value not in _LOOPBACK_HOSTS:
            raise ValueError("VERITAS_HOST must be a loopback address")
        return value

    @classmethod
    def from_env(cls) -> Settings:
        raw: dict[str, object] = {}
        if host := os.environ.get("VERITAS_HOST"):
            raw["host"] = host
        if port := os.environ.get("VERITAS_PORT"):
            raw["port"] = int(port)
        if db_path := os.environ.get("VERITAS_DB_PATH"):
            raw["db_path"] = Path(db_path)
        if cors_origin := os.environ.get("VERITAS_CORS_ORIGIN"):
            raw["cors_origin"] = cors_origin
        if scoring_mode := os.environ.get("VERITAS_SCORING_MODE"):
            raw["scoring_mode"] = scoring_mode
        if model_path := os.environ.get("VERITAS_MODEL_PATH"):
            raw["model_path"] = Path(model_path)
        if signing_key_path := os.environ.get("VERITAS_SIGNING_KEY_PATH"):
            raw["signing_key_path"] = Path(signing_key_path)
        if signing_key_id := os.environ.get("VERITAS_SIGNING_KEY_ID"):
            raw["signing_key_id"] = signing_key_id
        if chain_rpc_url := os.environ.get("VERITAS_CHAIN_RPC_URL"):
            raw["chain_rpc_url"] = chain_rpc_url
        if chain_id := os.environ.get("VERITAS_CHAIN_ID"):
            raw["chain_id"] = int(chain_id)
        if contract_address := os.environ.get("VERITAS_CONTRACT_ADDRESS"):
            raw["contract_address"] = contract_address
        return cls.model_validate(raw)

    @field_validator("scoring_mode")
    @classmethod
    def scoring_mode_is_known(cls, value: str) -> str:
        if value not in {"auto", "rule_only", "hybrid"}:
            raise ValueError("VERITAS_SCORING_MODE must be auto, rule_only, or hybrid")
        return value

    @field_validator("chain_rpc_url")
    @classmethod
    def chain_rpc_is_loopback(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in _LOOPBACK_HOSTS:
            raise ValueError("VERITAS_CHAIN_RPC_URL must use http on a loopback host")
        return value
