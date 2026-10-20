import { describe, expect, it } from "vitest";
import { describeApiError } from "./api";

describe("API error states", () => {
  it("explains an unreachable API", () => {
    expect(describeApiError(0, "NETWORK")).toMatch(/not reachable/);
  });

  it("explains missing records, conflicts, and dependency failures", () => {
    expect(describeApiError(404, "NOT_FOUND")).toMatch(/not found/);
    expect(describeApiError(409, "RESEED_REQUIRED")).toMatch(/already loaded/);
    expect(describeApiError(422, "VALIDATION_ERROR")).toMatch(/contract/);
    expect(describeApiError(503, "TRUST_REGISTRY_MISSING")).toMatch(/unavailable/);
    expect(describeApiError(500, "INTERNAL_ERROR")).toMatch(/error/);
  });
});
