export const API_BASE = "http://127.0.0.1:8000";

export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function describeApiError(status: number, code: string): string {
  if (status === 0 || code === "NETWORK") {
    return "The local API is not reachable.";
  }
  if (status === 404) return "That record was not found.";
  if (status === 409) return "The demo data is already loaded. Replace was not requested.";
  if (status === 422) return "The request did not match the API contract.";
  if (status === 503) return "A local dependency is unavailable.";
  if (status >= 500) return "The API returned an error.";
  return code || "The request failed.";
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiFailure(0, "NETWORK", describeApiError(0, "NETWORK"));
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      error?: { code?: string; message?: string };
    };
    const code = body.error?.code ?? "HTTP_ERROR";
    throw new ApiFailure(response.status, code, describeApiError(response.status, code));
  }
  return (await response.json()) as T;
}
