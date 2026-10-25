"use client";

import { useState } from "react";
import { type AmcPlan, type Price, TERRAIN_NOTE } from "@/lib/services";

const rupees = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;

/** Basic per-sq-ft price and AMC plans, with estimates for the visitor's plot size. */
export function PriceCard({ price, amc }: { price: Price; amc?: AmcPlan[] }) {
  const [sqft, setSqft] = useState("1200");
  const area = Number(sqft);
  const estimate = area > 0 ? Math.max(area * price.perSqft, price.minimum) : null;
  return (
    <div className="stack">
      <div className="svc-price">
        <div className="card">
          <p className="svc-eyebrow">Pay as you go</p>
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
      {amc?.length ? (
        <>
          <h3 className="svc-amc-title">Annual maintenance contracts (AMC)</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Pay once a year and save over paying per visit. Prices{area > 0 ? ` for a ${area.toLocaleString("en-IN")} sq ft plot` : ""}, before any difficult-terrain extra.
          </p>
          <div className="svc-amc">
            {amc.map((plan) => (
              <div key={plan.name} className={`card svc-plan${plan.popular ? " popular" : ""}`}>
                {plan.popular ? <span className="badge green">Recommended</span> : null}
                <h3>{plan.name}</h3>
                <p className="muted">{plan.summary}</p>
                <p className="svc-plan-price">
                  {area > 0 ? rupees(Math.max(area * plan.perSqftYear, plan.minimumYear)) : "—"} <span>a year</span>
                </p>
                <p className="small muted">
                  ₹{plan.perSqftYear} per sq ft a year, minimum {rupees(plan.minimumYear)}
                </p>
                <ul className="svc-ticks">
                  {plan.includes.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
