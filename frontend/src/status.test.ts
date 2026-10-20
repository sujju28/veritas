import { describe, expect, it } from "vitest";
import { statusLabel, statusTag } from "./status";

describe("status mapping", () => {
  it("maps anchor and verifier results onto the demo tags", () => {
    expect(statusTag("PENDING")).toBe("PENDING_ANCHOR");
    expect(statusTag("PENDING_ANCHOR")).toBe("PENDING_ANCHOR");
    expect(statusTag("CONFIRMED")).toBe("ANCHORED");
    expect(statusTag("VERIFIED_ONCHAIN")).toBe("ANCHORED");
    expect(statusTag("FAILED")).toBe("FAILED");
    expect(statusTag("CONFLICT")).toBe("FAILED");
    expect(statusTag("VERIFICATION_UNAVAILABLE")).toBe("VERIFICATION_UNAVAILABLE");
    expect(statusTag("TAMPERED")).toBe("SIGNATURE_MISMATCH");
    expect(statusTag("INVALID_SIGNATURE")).toBe("SIGNATURE_MISMATCH");
    expect(statusTag("ONCHAIN_MISMATCH")).toBe("SIGNATURE_MISMATCH");
    expect(statusLabel(statusTag("TAMPERED"))).toBe("Signature mismatch");
  });
});
