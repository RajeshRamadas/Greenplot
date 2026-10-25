"use client";

import { useState } from "react";
import { type Price, TERRAIN_NOTE } from "@/lib/services";

const rupees = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;

/** Basic per-sq-ft price with a quick estimate for a plot size. */
export function PriceCard({ price }: { price: Price }) {
  const [sqft, setSqft] = useState("1200");
  const area = Number(sqft);
  const estimate = area > 0 ? Math.max(area * price.perSqft, price.minimum) : null;
  return (
    <div className="svc-price">
      <div className="card">
        <p className="svc-eyebrow">Basic price</p>
        <p className="svc-rate">
          ₹{price.perSqft} <span>per sq ft, {price.per}</span>
        </p>
        <p className="small muted">Minimum {rupees(price.minimum)}.</p>
        <label className="svc-calc">
          <span>Your plot size (sq ft)</span>
          <input inputMode="numeric" value={sqft} onChange={(e) => setSqft(e.target.value.replace(/\D/g, ""))} placeholder="1200" />
        </label>
        <p className="svc-estimate">{estimate ? <>Basic estimate: <b>{rupees(estimate)}</b> {price.per}</> : "Enter your plot size"}</p>
      </div>
      <div className="alert info">
        <b>Difficult terrain costs extra.</b> {TERRAIN_NOTE}
      </div>
    </div>
  );
}
