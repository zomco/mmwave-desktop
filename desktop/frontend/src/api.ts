export interface ApiErrorShape {
  error: {
    code: string;
    message: string;
    request_id: string;
    details: Record<string, unknown>;
  };
}

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly requestId: string,
    readonly status: number,
    readonly details: Record<string, unknown>,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as ApiErrorShape | null;
    throw new ApiError(
      payload?.error.code ?? "REQUEST_FAILED",
      payload?.error.message ?? "TraceCue 请求失败。",
      payload?.error.request_id ?? "req_unknown",
      response.status,
      payload?.error.details ?? {},
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const post = <T>(path: string, value?: unknown) =>
  api<T>(path, { method: "POST", body: value === undefined ? undefined : JSON.stringify(value) });

export const patch = <T>(path: string, value: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(value) });

export const put = <T>(path: string, value: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(value) });

