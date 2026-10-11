import type { ErrorEnvelope, User } from "./types";

/** One fetch wrapper (spec §8.2): JWT + X-Request-ID, error envelope parsing, 401 -> logout. */

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const TOKEN_KEY = "migrateiq.session";

interface Session {
  token: string;
  user: User;
}

let session: Session | null = readStoredSession();
let onUnauthorized: (() => void) | null = null;

function readStoredSession(): Session | null {
  try {
    const raw = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function getSession(): Session | null {
  return session;
}

export function setSession(next: Session | null): void {
  session = next;
  try {
    if (next) sessionStorage.setItem(TOKEN_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: the in-memory copy still works for this tab */
  }
}

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(status: number, code: string, message: string, details: Record<string, unknown>, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Field-level validation issues ({path, code, message}) when the server sent them. */
  get fieldErrors(): { path: string; code: string; message: string }[] {
    const errors = this.details?.errors;
    return Array.isArray(errors) ? (errors as { path: string; code: string; message: string }[]) : [];
  }
}

export function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  headers?: Record<string, string>;
  query?: Record<string, string | number | boolean | null | undefined>;
  /** Return the raw Response (downloads). */
  raw?: boolean;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = `${API_BASE_URL}/api${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function apiRequest<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const requestId = newRequestId();
  const headers: Record<string, string> = { Accept: "application/json", "X-Request-ID": requestId, ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) {
    body = opts.body;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  if (session?.token) headers.Authorization = `Bearer ${session.token}`;

  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method: opts.method ?? "GET", headers, body, signal: opts.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the server. Check your connection and try again.", {}, requestId);
  }

  const echoedId = res.headers.get("X-Request-ID") ?? requestId;
  if (!res.ok) {
    let envelope: ErrorEnvelope | null = null;
    try {
      envelope = (await res.json()) as ErrorEnvelope;
    } catch {
      envelope = null;
    }
    const e = envelope?.error;
    const err = new ApiError(
      res.status,
      e?.code ?? (res.status >= 500 ? "INTERNAL" : "HTTP_ERROR"),
      e?.message ?? `Request failed with status ${res.status}.`,
      e?.details ?? {},
      e?.request_id ?? echoedId,
    );
    if (res.status === 401 && session) {
      setSession(null);
      onUnauthorized?.();
    }
    throw err;
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
