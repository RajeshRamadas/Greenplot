"use client";

import { useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { acceptFor, uploadEvidence } from "@/lib/capture";
import { label } from "@/lib/format";

/** Large camera/file button that hashes, geotags and uploads (or queues) evidence. */
export function CaptureButton({
  entityType,
  entityId,
  evidenceType,
  text,
  onDone,
  primary,
}: {
  entityType: string;
  entityId: string;
  evidenceType?: string;
  text?: string;
  onDone?: () => void;
  primary?: boolean;
}) {
  const { me } = useAuth();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const isDoc = evidenceType && ["invoice", "receipt", "service_report", "warranty", "document"].includes(evidenceType);

  async function onFiles(files: FileList | null) {
    if (!files?.length || !me) return;
    for (const file of Array.from(files)) {
      setProgress(0);
      try {
        const res = await uploadEvidence({
          file, entityType, entityId, evidenceType, userId: me.id, label: `${label(evidenceType || "file")} · ${file.name}`,
          onProgress: setProgress,
        });
        toast(res.status === "queued" ? "Saved offline — will upload when connected" : `${label(evidenceType || "File")} uploaded`);
      } catch (e) {
        toast((e as Error).message, "error");
      }
    }
    setProgress(null);
    if (input.current) input.current.value = "";
    onDone?.();
  }

  return (
    <div className="stack" style={{ gap: 6 }}>
      <button type="button" className={`btn ${primary ? "primary" : ""} block`} disabled={progress !== null} onClick={() => input.current?.click()}>
        <Icon name={isDoc ? "doc" : "camera"} />
        {progress !== null ? `Uploading ${Math.round(progress * 100)}%` : text || `Add ${label(evidenceType || "file").toLowerCase()}`}
      </button>
      {progress !== null ? (
        <div className="progress">
          <div style={{ width: `${Math.max(5, progress * 100)}%` }} />
        </div>
      ) : null}
      <input
        ref={input}
        type="file"
        hidden
        multiple={!isDoc}
        accept={acceptFor(evidenceType)}
        {...(!isDoc && evidenceType !== "video" ? { capture: "environment" as const } : {})}
        onChange={(e) => onFiles(e.target.files)}
      />
    </div>
  );
}
