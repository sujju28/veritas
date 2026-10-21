"""Tests for verifier ruleset checks, statuses, and strict mode (RSR-03 to RSR-05)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from veritas.evidence.models import EvidencePayload
from veritas.evidence.sign import sign_payload
from veritas.ledger.client import OnChainDecision
from veritas.ledger.commitment import decision_key
from veritas.ledger.ruleset import OnChainRuleset, ruleset_key
from veritas.risk.manifest import build_ruleset_manifest, ruleset_manifest_sha256
from veritas.verifier import check
from veritas.verifier.__main__ import main as verifier_main

_ADDR_DECISION = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
_ADDR_RULESET = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
_SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


class FakeLedgers:
    def __init__(self) -> None:
        self.decisions: dict[bytes, bytes] = {}
        self.rulesets: dict[bytes, OnChainRuleset] = {}

    def get_decision(self, key: bytes) -> OnChainDecision:
        digest = self.decisions.get(key)
        if digest is None:
            return OnChainDecision(False, bytes(32), "0x" + "00" * 20, 0, 0)
        return OnChainDecision(True, digest, _SENDER.lower(), 1, 100)

    def get_ruleset(self, key: bytes) -> OnChainRuleset:
        item = self.rulesets.get(key)
        if item is None:
            return OnChainRuleset(False, bytes(32), False, "0x" + "00" * 20, 0, 0)
        return item


def _setup_fixture(tmp_path: Path) -> tuple[dict, dict, Ed25519PrivateKey, FakeLedgers]:
    priv = Ed25519PrivateKey.generate()
    pub_b64 = base64.b64encode(priv.public_key().public_bytes_raw()).decode("ascii")
    registry = {
        "keys": [
            {
                "key_id": "issuer-1",
                "algorithm": "Ed25519",
                "public_key_b64": pub_b64,
            }
        ]
    }
    ledgers = FakeLedgers()
    return registry, {}, priv, ledgers


def _patch_clients(monkeypatch, ledgers: FakeLedgers) -> None:
    class MockDecisionClient:
        def __init__(self, config: object) -> None:
            pass

        def validate(self) -> None:
            pass

        def get_decision(self, key: bytes) -> OnChainDecision:
            return ledgers.get_decision(key)

    class MockRulesetClient:
        def __init__(self, config: object) -> None:
            pass

        def validate(self) -> None:
            pass

        def get_ruleset(self, key: bytes) -> OnChainRuleset:
            return ledgers.get_ruleset(key)

    monkeypatch.setattr(check, "LedgerClient", MockDecisionClient)
    monkeypatch.setattr(check, "RulesetClient", MockRulesetClient)


def test_rsr_03_honest_1_1_receipt_registered_ruleset(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    manifest_hash = ruleset_manifest_sha256()
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-03",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")

    # Seed ledgers
    dec_k = decision_key("dec-rsr-03")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    rule_k = ruleset_key("rules-v1")
    ledgers.rulesets[rule_k] = OnChainRuleset(
        exists=True,
        manifest_sha256=bytes.fromhex(manifest_hash),
        deprecated=False,
        sender=_SENDER,
        block_number=1,
        timestamp=100,
    )

    result = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert result["status"] == "VERIFIED_ONCHAIN"
    assert result["ruleset_check"] == "MATCH"

    # Test CLI exit 0
    rcpt_file = tmp_path / "receipt.json"
    rcpt_file.write_text(json.dumps(receipt.model_dump()))
    reg_file = tmp_path / "trust.json"
    reg_file.write_text(json.dumps(registry))

    exit_code = verifier_main(
        [
            "verify",
            "--receipt",
            str(rcpt_file),
            "--trusted-keys",
            str(reg_file),
            "--chain-id",
            "31337",
            "--contract-address",
            _ADDR_DECISION,
            "--ruleset-address",
            _ADDR_RULESET,
            "--json",
        ]
    )
    assert exit_code == 0


def test_rsr_04_mismatched_ruleset_sha256(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    # Receipt signed with different ruleset_sha256
    different_hash = "00" * 32
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-04",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=different_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")

    # Decision on chain matches this receipt's digest
    dec_k = decision_key("dec-rsr-04")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    # But ruleset on chain has legitimate hash
    real_manifest_hash = ruleset_manifest_sha256()
    rule_k = ruleset_key("rules-v1")
    ledgers.rulesets[rule_k] = OnChainRuleset(
        exists=True,
        manifest_sha256=bytes.fromhex(real_manifest_hash),
        deprecated=False,
        sender=_SENDER,
        block_number=1,
        timestamp=100,
    )

    result = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert result["status"] == "RULESET_MISMATCH"
    assert result["ruleset_check"] == "MISMATCH"

    # Unsigned edit gives TAMPERED
    tampered_data = receipt.model_dump()
    tampered_data["payload"]["ruleset_sha256"] = real_manifest_hash
    tampered_result = check.verify_on_chain(
        tampered_data,
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert tampered_result["status"] == "TAMPERED"


def test_rsr_05_unregistered_version(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    manifest_hash = ruleset_manifest_sha256()
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-05-unreg",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v999",  # unreg
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")
    dec_k = decision_key("dec-rsr-05-unreg")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    result = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert result["status"] == "RULESET_UNREGISTERED"
    assert result["ruleset_check"] == "UNREGISTERED"


def test_rsr_05_manifest_file_mismatch(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    manifest_hash = ruleset_manifest_sha256()
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-05-mismatch",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")
    dec_k = decision_key("dec-rsr-05-mismatch")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    rule_k = ruleset_key("rules-v1")
    ledgers.rulesets[rule_k] = OnChainRuleset(
        exists=True,
        manifest_sha256=bytes.fromhex(manifest_hash),
        deprecated=False,
        sender=_SENDER,
        block_number=1,
        timestamp=100,
    )

    # Point to an altered manifest file
    edited_manifest = tmp_path / "altered_rules.json"
    alt_data = build_ruleset_manifest()
    alt_data["rules"][0]["threshold"] = 999.0
    edited_manifest.write_text(json.dumps(alt_data), encoding="utf-8")

    result = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
        manifest_path=edited_manifest,
    )
    assert result["status"] == "MANIFEST_MISMATCH"
    assert result["ruleset_check"] == "MANIFEST_MISMATCH"


def test_deprecated_ruleset_is_verified_onchain(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    manifest_hash = ruleset_manifest_sha256()
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-dep",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")
    dec_k = decision_key("dec-rsr-dep")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    rule_k = ruleset_key("rules-v1")
    ledgers.rulesets[rule_k] = OnChainRuleset(
        exists=True,
        manifest_sha256=bytes.fromhex(manifest_hash),
        deprecated=True,  # deprecated
        sender=_SENDER,
        block_number=1,
        timestamp=100,
    )

    result = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert result["status"] == "VERIFIED_ONCHAIN"
    assert result["ruleset_check"] == "DEPRECATED"


def test_golden_1_0_receipt_ruleset_check_not_applicable(monkeypatch, tmp_path: Path) -> None:
    _, _, _, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "golden_receipt_v1_0.json"
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    receipt = data["receipt"]
    registry = data["trust_registry"]

    dec_k = decision_key("dec-golden-001")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt["digest_hex"])

    result = check.verify_on_chain(
        receipt,
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=_ADDR_RULESET,
    )
    assert result["status"] == "VERIFIED_ONCHAIN"
    assert result["ruleset_check"] == "NOT_CHECKED"


def test_protocol_1_1_opt_out_without_ruleset_address(monkeypatch, tmp_path: Path) -> None:
    registry, _, priv, ledgers = _setup_fixture(tmp_path)
    _patch_clients(monkeypatch, ledgers)

    manifest_hash = ruleset_manifest_sha256()
    payload = EvidencePayload(
        schema_version="1.1",
        decision_id="dec-rsr-opt",
        transaction_id="txn-001",
        bank_id="BANK_A",
        decision="LOW",
        risk_score=20,
        reason_codes=["FAN_IN"],
        feature_snapshot_sha256="aa" * 32,
        model_version="rule-only",
        ruleset_version="rules-v1",
        ruleset_sha256=manifest_hash,
        decision_timestamp="2026-10-20T12:00:00Z",
    )
    receipt, _ = sign_payload(payload, priv, "issuer-1")
    dec_k = decision_key("dec-rsr-opt")
    ledgers.decisions[dec_k] = bytes.fromhex(receipt.digest_hex)

    # Without allow_unchecked_ruleset -> RULESET_UNCHECKED
    res_strict = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=None,
        allow_unchecked_ruleset=False,
    )
    assert res_strict["status"] == "RULESET_UNCHECKED"

    # With allow_unchecked_ruleset -> VERIFIED_ONCHAIN
    res_opt = check.verify_on_chain(
        receipt.model_dump(),
        registry,
        rpc_url="http://127.0.0.1:8545",
        chain_id=31337,
        contract_address=_ADDR_DECISION,
        ruleset_registry_address=None,
        allow_unchecked_ruleset=True,
    )
    assert res_opt["status"] == "VERIFIED_ONCHAIN"
    assert res_opt["ruleset_check"] == "NOT_CHECKED"
