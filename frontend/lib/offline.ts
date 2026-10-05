"use client";

/**
 * Offline-tolerant queue (requirements §30).
 *
 * Operations and captured media are stored in IndexedDB with a client_op_id /
 * client_ref, then replayed to /sync and /media/direct when the device is
 * online. The server de-duplicates on those ids, so retries are always safe.
 *
 * States: QUEUED → SYNCING → SYNCED / FAILED / RETRY (and CONFLICT from the server).
 */

import { api, authHeader } from "./api";

const DB_NAME = "greenplot-offline";
const OPS = "ops";
const BLOBS = "blobs";

export type SyncState = "queued" | "syncing" | "synced" | "failed" | "retry" | "conflict";

export interface QueuedOp {
  client_op_id: string;
  entity: string;
  operation: string;
  payload: Record<string, unknown>;
  client_timestamp: string;
  user_id: string;
  label: string;
  state: SyncState;
  attempts: number;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

export interface QueuedBlob {
  client_ref: string;
  entity_type: string;
  entity_id: string;
  evidence_type?: string;
  filename: string;
  content_type: string;
  blob: Blob;
  sha256: string;
  captured_at: string;
  latitude?: number | null;
  longitude?: number | null;
  user_id: string;
  label: string;
  state: SyncState;
  attempts: number;
  error?: string | null;
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(OPS)) db.createObjectStore(OPS, { keyPath: "client_op_id" });
      if (!db.objectStoreNames.contains(BLOBS)) db.createObjectStore(BLOBS, { keyPath: "client_ref" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const req = fn(t.objectStore(store));
    t.oncomplete = () => resolve(req ? (req as IDBRequest<T>).result : undefined);
    t.onerror = () => reject(t.error);
  });
}

const all = <T,>(store: string) => tx<T[]>(store, "readonly", (s) => s.getAll() as IDBRequest<T[]>).then((r) => r || []);
const put = (store: string, value: unknown) => tx(store, "readwrite", (s) => s.put(value));
const del = (store: string, key: string) => tx(store, "readwrite", (s) => s.delete(key));

export function newId(prefix = "op") {
  const rnd = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
  return `${prefix}-${rnd}`;
}

const changeListeners = new Set<() => void>();
export function onQueueChange(fn: () => void) {
  changeListeners.add(fn);
  return () => void changeListeners.delete(fn);
}
const emit = () => changeListeners.forEach((f) => f());

export async function enqueue(userId: string, entity: string, operation: string, payload: Record<string, unknown>, label: string, id?: string) {
  const op: QueuedOp = {
    client_op_id: id || newId(entity),
    entity,
    operation,
    payload,
    client_timestamp: new Date().toISOString(),
    user_id: userId,
    label,
    state: "queued",
    attempts: 0,
  };
  await put(OPS, op);
  emit();
  void flush();
  return op;
}

export async function enqueueBlob(b: Omit<QueuedBlob, "state" | "attempts">) {
  await put(BLOBS, { ...b, state: "queued", attempts: 0 });
  emit();
  void flush();
}

export async function listQueue() {
  const [ops, blobs] = await Promise.all([all<QueuedOp>(OPS), all<QueuedBlob>(BLOBS)]);
  return { ops: ops.sort((a, b) => a.client_timestamp.localeCompare(b.client_timestamp)), blobs };
}

export async function clearSynced() {
  const { ops, blobs } = await listQueue();
  await Promise.all([
    ...ops.filter((o) => o.state === "synced").map((o) => del(OPS, o.client_op_id)),
    ...blobs.filter((b) => b.state === "synced").map((b) => del(BLOBS, b.client_ref)),
  ]);
  emit();
}

export async function discard(kind: "op" | "blob", key: string) {
  await del(kind === "op" ? OPS : BLOBS, key);
  emit();
}

let flushing = false;

/** Push queued work to the server. Safe to call often. */
export async function flush(): Promise<void> {
  if (flushing || typeof navigator === "undefined" || !navigator.onLine) return;
  flushing = true;
  try {
    const { ops, blobs } = await listQueue();
    const pending = ops.filter((o) => ["queued", "retry", "syncing"].includes(o.state));
    if (pending.length) {
      for (const o of pending) await put(OPS, { ...o, state: "syncing" });
      emit();
      try {
        const res = await api<{ results: { client_op_id: string; status: SyncState; result: Record<string, unknown> | null; error: string | null }[] }>(
          "/sync",
          { body: { device_id: deviceId(), operations: pending.map(({ client_op_id, entity, operation, payload, client_timestamp }) => ({ client_op_id, entity, operation, payload, client_timestamp })) } },
        );
        const byId = new Map(res.results.map((r) => [r.client_op_id, r]));
        for (const o of pending) {
          const r = byId.get(o.client_op_id);
          await put(OPS, { ...o, state: r?.status ?? "retry", result: r?.result ?? null, error: r?.error ?? null, attempts: o.attempts + 1 });
        }
      } catch (e) {
        for (const o of pending) await put(OPS, { ...o, state: "retry", error: (e as Error).message, attempts: o.attempts + 1 });
      }
      emit();
    }
    for (const b of blobs.filter((x) => ["queued", "retry", "syncing"].includes(x.state))) {
      await put(BLOBS, { ...b, state: "syncing" });
      emit();
      try {
        const fd = new FormData();
        fd.append("file", new File([b.blob], b.filename, { type: b.content_type }));
        fd.append("entity_type", b.entity_type);
        fd.append("entity_id", b.entity_id);
        if (b.evidence_type) fd.append("evidence_type", b.evidence_type);
        fd.append("sha256", b.sha256);
        fd.append("captured_at", b.captured_at);
        fd.append("client_ref", b.client_ref);
        if (b.latitude != null) fd.append("latitude", String(b.latitude));
        if (b.longitude != null) fd.append("longitude", String(b.longitude));
        const r = await fetch("/api/v1/media/direct", { method: "POST", body: fd, headers: authHeader() });
        if (r.ok) await put(BLOBS, { ...b, state: "synced", error: null, attempts: b.attempts + 1 });
        else {
          const detail = await r.json().catch(() => ({}));
          const msg = typeof detail?.detail === "string" ? detail.detail : JSON.stringify(detail?.detail ?? r.status);
          await put(BLOBS, { ...b, state: r.status >= 500 || r.status === 401 ? "retry" : "failed", error: msg, attempts: b.attempts + 1 });
        }
      } catch (e) {
        await put(BLOBS, { ...b, state: "retry", error: (e as Error).message, attempts: b.attempts + 1 });
      }
      emit();
    }
  } finally {
    flushing = false;
  }
}

export function deviceId(): string {
  try {
    let id = localStorage.getItem("gp.device");
    if (!id) {
      id = newId("device");
      localStorage.setItem("gp.device", id);
    }
    return id;
  } catch {
    return "unknown-device";
  }
}

let started = false;
export function startSyncLoop() {
  if (started || typeof window === "undefined") return;
  started = true;
  window.addEventListener("online", () => void flush());
  setInterval(() => void flush(), 30_000);
  void flush();
}
