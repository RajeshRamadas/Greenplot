import type { Metadata } from "next";
import { Checkout } from "@/components/Store";
import { StoreShell } from "@/components/StoreShell";
import { getStoreConfig } from "@/lib/store";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Checkout", robots: { index: false, follow: false } };

export default async function CheckoutPage() {
  const cfg = await getStoreConfig();
  return (
    <StoreShell>
      <main className="svc-wrap">
        <h1 className="store-h1">Checkout</h1>
        <Checkout cfg={cfg} />
      </main>
    </StoreShell>
  );
}
