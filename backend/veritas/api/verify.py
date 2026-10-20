"""Verify a caller-supplied receipt copy. This route does not score or store it."""

from fastapi import APIRouter, Request

from veritas.api.errors import ApiError
from veritas.api.settings import Settings
from veritas.evidence.keys import SigningKeyError, load_trust_registry, registry_path_for
from veritas.evidence.models import EvidenceReceipt
from veritas.evidence.verify import SIGNATURE_VALID_OFFLINE, verify_offline
from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.verifier.check import verify_on_chain

router = APIRouter(prefix="/api/v1")


@router.post("/verify")
def verify_copy(body: EvidenceReceipt, request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    registry_path = registry_path_for(settings.signing_key_path)
    try:
        registry = load_trust_registry(registry_path).model_dump()
    except (OSError, SigningKeyError) as exc:
        raise ApiError(
            "TRUST_REGISTRY_MISSING", "pinned public keys are not available", 503
        ) from exc
    receipt = body.model_dump()
    offline = verify_offline(receipt, registry)
    if offline["status"] != SIGNATURE_VALID_OFFLINE or not settings.contract_address:
        status = (
            offline["status"]
            if offline["status"] != SIGNATURE_VALID_OFFLINE
            else "VERIFICATION_UNAVAILABLE"
        )
        return {
            "status": status,
            "digest_hex": offline.get("digest_hex"),
            "signing_key_id": offline.get("signing_key_id"),
            "stored": False,
        }
    result = verify_on_chain(
        receipt,
        registry,
        rpc_url=settings.chain_rpc_url,
        chain_id=settings.chain_id,
        contract_address=settings.contract_address,
        runtime_code_sha256=PINNED_RUNTIME_SHA256,
    )
    return {
        "status": result["status"],
        "digest_hex": result.get("digest_hex"),
        "signing_key_id": result.get("signing_key_id"),
        "stored": False,
    }
