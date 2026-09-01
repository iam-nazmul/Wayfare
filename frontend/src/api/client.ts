import { ApiError, toProblem } from './problem';

const BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

const ACCESS_KEY = 'wf_access';

let refreshInflight: Promise<string | null> | null = null;

export function setAccessToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(ACCESS_KEY, token);
    else localStorage.removeItem(ACCESS_KEY);
  } catch {
    /* storage blocked — the session simply will not survive a reload */
  }
}

export function getAccessToken(): string | null {
  try {
    return localStorage.getItem(ACCESS_KEY);
  } catch {
    return null;
  }
}

/** One in-flight refresh; concurrent 401s queue behind it instead of stampeding. */
async function refreshAccessToken(): Promise<string | null> {
  refreshInflight ??= (async () => {
    try {
      const response = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: '{}',
      });
      if (!response.ok) return null;
      const data = (await response.json()) as { access?: string };
      if (!data.access) return null;
      setAccessToken(data.access);
      return data.access;
    } catch {
      return null;
    } finally {
      refreshInflight = null;
    }
  })();

  return refreshInflight;
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Send an Idempotency-Key. Required by the API for booking, payment and refund creation. */
  idempotent?: boolean;
  /** Optimistic-concurrency guard on booking mutations. */
  ifMatch?: string;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, idempotent, ifMatch, headers, ...rest } = options;

  const send = async (token: string | null): Promise<Response> => {
    const finalHeaders = new Headers(headers);
    finalHeaders.set('Accept', 'application/json');
    if (body !== undefined) finalHeaders.set('Content-Type', 'application/json');
    if (token) finalHeaders.set('Authorization', `Bearer ${token}`);
    if (idempotent) finalHeaders.set('Idempotency-Key', crypto.randomUUID());
    if (ifMatch) finalHeaders.set('If-Match', ifMatch);

    return fetch(`${BASE}${path}`, {
      ...rest,
      headers: finalHeaders,
      credentials: 'include',
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  };

  let response = await send(getAccessToken());

  if (response.status === 401) {
    const token = await refreshAccessToken();
    if (token) response = await send(token);
  }

  if (response.status === 204) return undefined as T;

  const payload = await response.json().catch(() => null);

  if (!response.ok) throw new ApiError(toProblem(response.status, payload));

  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};
