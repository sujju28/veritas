export const STATUS_TAGS = [
  "PENDING_ANCHOR",
  "ANCHORED",
  "FAILED",
  "VERIFICATION_UNAVAILABLE",
  "SIGNATURE_MISMATCH",
] as const;

export type StatusTag = (typeof STATUS_TAGS)[number];

const LABELS: Record<StatusTag, string> = {
  PENDING_ANCHOR: "Pending anchor",
  ANCHORED: "Anchored",
  FAILED: "Failed",
  VERIFICATION_UNAVAILABLE: "Verification unavailable",
  SIGNATURE_MISMATCH: "Signature mismatch",
};

export function statusTag(raw: string | null | undefined): StatusTag {
  const value = (raw ?? "").toUpperCase();
  if (
    value === "CONFIRMED" ||
    value === "ANCHORED" ||
    value === "VERIFIED_ONCHAIN" ||
    value === "SIGNED"
  ) {
    return value === "SIGNED" ? "PENDING_ANCHOR" : "ANCHORED";
  }
  if (value === "VERIFICATION_UNAVAILABLE") return "VERIFICATION_UNAVAILABLE";
  if (
    value === "TAMPERED" ||
    value === "INVALID_SIGNATURE" ||
    value === "ONCHAIN_MISMATCH" ||
    value === "UNKNOWN_ISSUER" ||
    value === "SIGNATURE_MISMATCH"
  ) {
    return "SIGNATURE_MISMATCH";
  }
  if (
    value === "FAILED" ||
    value === "CONFLICT" ||
    value === "REJECTED" ||
    value === "CONFIG_MISMATCH" ||
    value === "DIGEST_CONFLICT" ||
    value === "CONTRACT_REJECTED"
  ) {
    return "FAILED";
  }
  return "PENDING_ANCHOR";
}

export function statusLabel(tag: StatusTag): string {
  return LABELS[tag];
}
