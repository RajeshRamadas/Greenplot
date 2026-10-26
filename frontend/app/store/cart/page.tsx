import type { Metadata } from "next";
import { CartView } from "@/components/Store";
import { StoreShell } from "@/components/StoreShell";
import { getStoreConfig } from "@/lib/store";

export const dynamic = "force-dynamic";

export const metadata: Metadata = { title: "Your cart", robots: { index: false, follow: true } };

export default async function CartPage() {
  const cfg = await getStoreConfig();
  return (
    <StoreShell>
      <main className="svc-wrap">
        <h1 className="store-h1">Your cart</h1>
        <CartView cfg={cfg} />
      </main>
    </StoreShell>
  );
}
