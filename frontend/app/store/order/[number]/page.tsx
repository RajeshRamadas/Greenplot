import type { Metadata } from "next";
import { Suspense } from "react";
import { OrderView } from "@/components/Store";
import { StoreShell } from "@/components/StoreShell";

export const metadata: Metadata = { title: "Your order", robots: { index: false, follow: false } };

export default async function OrderPage({ params }: { params: Promise<{ number: string }> }) {
  const { number } = await params;
  return (
    <StoreShell>
      <main className="svc-wrap">
        <Suspense fallback={<div className="card store-empty">Loading your order…</div>}>
          <OrderView number={number} />
        </Suspense>
      </main>
    </StoreShell>
  );
}
