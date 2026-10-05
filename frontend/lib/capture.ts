"use client";

/** Evidence capture: hash on device, attach GPS, upload via signed URL, or queue when offline. */

import { api } from "./api";
import { enqueueBlob, newId } from "./offline";
import type { MediaItem } from "./types";

export async function sha256Hex(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface Position {
  latitude: number;
  longitude: number;
  accuracy_m: number;
}

/** Best-effort location. GPS is supporting evidence only; failures resolve to null. */
export function getPosition(timeoutMs = 5000): Promise<Position | null> {
  return new Promise((resolve) => {
    if (typeof navigator === "undefined" || !navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ latitude: p.coords.latitude, longitude: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    );
  });
}

export interface UploadArgs {
  file: File;
  entityType: string;
  entityId: string;
  evidenceType?: string;
  userId: string;
  label?: string;
  replaces?: string;
  onProgress?: (fraction: number) => void;
}

export type UploadResult = { status: "uploaded"; media: MediaItem } | { status: "queued" };

const ALLOWED = ["image/jpeg", "image/png", "image/webp", "image/heic", "video/mp4", "video/quicktime", "video/webm", "application/pdf"];

export function acceptFor(evidenceType?: string) {
  if (!evidenceType) return ALLOWED.join(",");
  if (evidenceType === "video") return "video/*";
  if (["invoice", "receipt", "service_report", "warranty", "document"].includes(evidenceType)) return "application/pdf,image/*";
  return "image/*";
}

export async function uploadEvidence(a: UploadArgs): Promise<UploadResult> {
  const contentType = a.file.type || "application/octet-stream";
  if (!ALLOWED.includes(contentType)) throw new Error(`Unsupported file type ${contentType}`);
  const [sha256, pos] = await Promise.all([sha256Hex(a.file), getPosition(4000)]);
  const capturedAt = new Date(a.file.lastModified || Date.now()).toISOString();
  const clientRef = newId("media");

  if (!navigator.onLine) {
    await enqueueBlob({
      client_ref: clientRef, entity_type: a.entityType, entity_id: a.entityId, evidence_type: a.evidenceType, filename: a.file.name || "capture",
      content_type: contentType, blob: a.file, sha256, captured_at: capturedAt, latitude: pos?.latitude, longitude: pos?.longitude,
      user_id: a.userId, label: a.label || a.evidenceType || "file",
    });
    return { status: "queued" };
  }

  const req = await api<{ media_id: string; upload: { method: string; url: string; headers: Record<string, string> } | null }>("/media/upload-url", {
    body: {
      entity_type: a.entityType, entity_id: a.entityId, content_type: contentType, size_bytes: a.file.size, sha256,
      filename: a.file.name || "capture", evidence_type: a.evidenceType, captured_at: capturedAt,
      latitude: pos?.latitude, longitude: pos?.longitude, client_ref: clientRef, replaces_media_id: a.replaces,
    },
  });
  if (req.upload) {
    await putWithProgress(req.upload.url, req.upload.headers, a.file, a.onProgress);
  }
  const media = await api<MediaItem>("/media/complete", { body: { media_id: req.media_id } });
  return { status: "uploaded", media };
}

function putWithProgress(url: string, headers: Record<string, string>, body: Blob, onProgress?: (f: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    Object.entries(headers).forEach(([k, v]) => xhr.setRequestHeader(k, v));
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
    xhr.onload = () => (xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`)));
    xhr.onerror = () => reject(new Error("Network error during upload"));
    xhr.send(body);
  });
}
