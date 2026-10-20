"""Local Ed25519 issuer key and a separate pinned public-key registry."""

from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field

from veritas.evidence.models import SIGNATURE_ALGORITHM


class SigningKeyError(Exception):
    pass


class TrustedKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")
    algorithm: str = Field(pattern=r"^Ed25519$")
    public_key_b64: str = Field(min_length=1, max_length=128)


class TrustRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keys: list[TrustedKey]


def ensure_signing_key(path: Path, key_id: str) -> Path:
    """Create a mode-0600 private key and a sibling public registry when missing."""
    if path.exists():
        if not path.is_file():
            raise SigningKeyError("signing key path is not a file")
        _require_private_mode(path)
        registry = registry_path_for(path)
        if not registry.is_file():
            raise SigningKeyError("pinned trust registry is missing")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(pem)
    _require_private_mode(path)
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    registry = TrustRegistry(
        keys=[
            TrustedKey(
                key_id=key_id,
                algorithm=SIGNATURE_ALGORITHM,
                public_key_b64=base64.b64encode(public).decode("ascii"),
            )
        ]
    )
    registry_path_for(path).write_text(
        json.dumps(registry.model_dump(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_private_key(path: Path) -> Ed25519PrivateKey:
    try:
        _require_private_mode(path)
        pem = path.read_bytes()
    except OSError as exc:
        raise SigningKeyError("signing key is not readable") from exc
    if b"PRIVATE KEY" not in pem:
        raise SigningKeyError("signing key is not a private key")
    try:
        loaded = serialization.load_pem_private_key(pem, password=None)
    except ValueError as exc:
        raise SigningKeyError("signing key could not be parsed") from exc
    if not isinstance(loaded, Ed25519PrivateKey):
        raise SigningKeyError("signing key is not Ed25519")
    return loaded


def load_trust_registry(path: Path) -> TrustRegistry:
    text = path.read_text(encoding="utf-8")
    if "PRIVATE KEY" in text:
        raise SigningKeyError("trust registry must contain public keys only")
    return TrustRegistry.model_validate_json(text)


def public_key_from_b64(value: str) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(value, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError) as exc:
        raise SigningKeyError("pinned public key is not Ed25519") from exc


def registry_path_for(private_key_path: Path) -> Path:
    return private_key_path.with_name("trust-registry.json")


def _require_private_mode(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise SigningKeyError("signing key must not be group or world accessible")
