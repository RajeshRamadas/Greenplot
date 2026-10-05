"use client";

import { useEffect, useRef, useState } from "react";

type Detector = { detect: (src: HTMLVideoElement) => Promise<{ rawValue: string }[]> };

/**
 * QR scanning via the browser BarcodeDetector API, NFC via Web NFC where available,
 * and manual entry as a fallback (requirements §9 QR/NFC asset scan).
 */
export function QrScanner({ onCode, allowNfc = true }: { onCode: (code: string, method: "qr" | "nfc" | "manual") => void; allowNfc?: boolean }) {
  const video = useRef<HTMLVideoElement>(null);
  const [active, setActive] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const supportsQr = typeof window !== "undefined" && "BarcodeDetector" in window;
  const supportsNfc = typeof window !== "undefined" && "NDEFReader" in window;

  useEffect(() => {
    if (!active) return;
    let stream: MediaStream | null = null;
    let stop = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (!video.current) return;
        video.current.srcObject = stream;
        await video.current.play();
        const Ctor = (window as unknown as { BarcodeDetector: new (o: object) => Detector }).BarcodeDetector;
        const detector = new Ctor({ formats: ["qr_code"] });
        while (!stop) {
          const codes = await detector.detect(video.current).catch(() => []);
          if (codes.length) {
            setActive(false);
            onCode(codes[0].rawValue, "qr");
            return;
          }
          await new Promise((r) => setTimeout(r, 250));
        }
      } catch (e) {
        setMsg(`Camera unavailable: ${(e as Error).message}`);
        setActive(false);
      }
    })();
    return () => {
      stop = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [active, onCode]);

  async function readNfc() {
    try {
      const Reader = (window as unknown as { NDEFReader: new () => { scan: () => Promise<void>; onreading: (e: { serialNumber: string }) => void } }).NDEFReader;
      const r = new Reader();
      await r.scan();
      setMsg("Hold the phone near the NFC tag…");
      r.onreading = (e) => {
        setMsg(null);
        onCode(e.serialNumber, "nfc");
      };
    } catch (e) {
      setMsg(`NFC unavailable: ${(e as Error).message}`);
    }
  }

  return (
    <div className="stack scanner">
      {active ? <video ref={video} muted playsInline /> : null}
      <div className="row">
        {supportsQr ? (
          <button type="button" className="btn primary" onClick={() => setActive((a) => !a)}>
            {active ? "Stop camera" : "Scan QR code"}
          </button>
        ) : (
          <span className="small muted">QR scanning needs a browser with camera barcode support; enter the code below.</span>
        )}
        {allowNfc && supportsNfc ? (
          <button type="button" className="btn" onClick={readNfc}>
            Read NFC tag
          </button>
        ) : null}
      </div>
      {msg ? <div className="alert info">{msg}</div> : null}
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          if (manual.trim()) onCode(manual.trim(), "manual");
        }}
      >
        <input placeholder="Or type the code on the label" value={manual} onChange={(e) => setManual(e.target.value)} style={{ flex: 1, minWidth: 180 }} />
        <button className="btn">Use code</button>
      </form>
    </div>
  );
}
