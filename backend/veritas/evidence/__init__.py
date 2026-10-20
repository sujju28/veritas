"""Canonical receipts and detached Ed25519 signatures."""

from veritas.evidence.models import EvidencePayload, EvidenceReceipt
from veritas.evidence.verify import verify_offline

__all__ = ["EvidencePayload", "EvidenceReceipt", "verify_offline"]
