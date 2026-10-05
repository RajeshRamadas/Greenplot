"use client";

/**
 * API client. Talks to the FastAPI backend through the same-origin /api/v1 rewrite.
 * The access token lives in memory; the refresh token in localStorage so a PWA
 * restart can resume the session. Tokens rotate on every refresh.
 */

const BASE = "/api/v1";
const REFRESH_KEY = "gp.refresh";

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(messageOf(detail) || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

function messageOf(detail: unknown): string {
  if (!detail) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: (string | number)[]; msg?: string }) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`)
      .join("; ");
  }
  if (typeof detail === "object" && detail && "message" in detail) {
    const d = detail as { message: string; missing?: string[] };
    return d.missing?.length ? `${d.message}: ${d.missing.map((m) => m.replace(/_/g, " ")).join(", ")}` : d.message;
  }
  return JSON.stringify(detail);
}

function storage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}

export function getRefreshToken(): string | null {
  return storage()?.getItem(REFRESH_KEY) ?? null;
}

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access;
  const s = storage();
  if (s) {
    if (refresh) s.setItem(REFRESH_KEY, refresh);
    else s.removeItem(REFRESH_KEY);
  }
  listeners.forEach((l) => l());
}

export function onAuthChange(fn: () => void) {
  listeners.add(fn);
  return () => void listeners.delete(fn);
}

export function hasAccessToken() {
  return !!accessToken;
}

async function refresh(): Promise<boolean> {
  const token = getRefreshToken();
  if (!token) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const r = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: token }),
        });
        if (!r.ok) {
          setTokens(null, null);
          return false;
        }
        const data = await r.json();
        setTokens(data.access_token, data.refresh_token);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null | string[]>;
  headers?: Record<string, string>;
  raw?: boolean;
}

export function qs(query?: RequestOptions["query"]): string {
  if (!query) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  if (!accessToken && getRefreshToken()) await refresh();
  const doFetch = () =>
    fetch(`${BASE}${path}${qs(opts.query)}`, {
      method: opts.method || (opts.body !== undefined ? "POST" : "GET"),
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...opts.headers,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  let r = await doFetch();
  if (r.status === 401 && (await refresh())) r = await doFetch();
  if (opts.raw) {
    if (!r.ok) throw new ApiError(r.status, await safeJson(r));
    return r as unknown as T;
  }
  const data = await safeJson(r);
  if (!r.ok) throw new ApiError(r.status, (data as { detail?: unknown })?.detail ?? data);
  return data as T;
}

async function safeJson(r: Response): Promise<unknown> {
  const text = await r.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export async function login(email: string, password: string) {
  const r = await fetch(`${BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, device: navigator.userAgent.slice(0, 180) }),
  });
  const data = await safeJson(r);
  if (!r.ok) throw new ApiError(r.status, (data as { detail?: unknown })?.detail);
  const t = data as { access_token: string; refresh_token: string };
  setTokens(t.access_token, t.refresh_token);
}

export async function acceptInvite(token: string, password: string) {
  const r = await fetch(`${BASE}/auth/accept-invite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, password }),
  });
  const data = await safeJson(r);
  if (!r.ok) throw new ApiError(r.status, (data as { detail?: unknown })?.detail);
  const t = data as { access_token: string; refresh_token: string };
  setTokens(t.access_token, t.refresh_token);
}

export async function logout() {
  const token = getRefreshToken();
  if (token) {
    try {
      await api("/auth/logout", { body: { refresh_token: token } });
    } catch {
      /* best effort */
    }
  }
  setTokens(null, null);
}

/** Download an authenticated file (PDF/CSV) and hand it to the browser. */
export async function download(path: string, query?: RequestOptions["query"], filename?: string) {
  const r = await api<Response>(path, { query, raw: true });
  const blob = await r.blob();
  const name = filename || r.headers.get("content-disposition")?.match(/filename="?([^"]+)"?/)?.[1] || "download";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function authHeader(): Record<string, string> {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}
