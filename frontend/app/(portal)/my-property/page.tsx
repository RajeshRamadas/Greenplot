"use client";

import { PropertyView } from "@/components/PropertyView";
import { Empty, Loading } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { Page, Property } from "@/lib/types";

export default function MyPropertyPage() {
  const { data, loading } = useApi<Page<Property>>("/properties");
  if (loading && !data) return <Loading />;
  if (!data?.items.length) return <Empty title="No property linked to your account">Ask your layout association to link your plot.</Empty>;
  return (
    <div className="stack" style={{ gap: 32 }}>
      {data.items.map((p) => (
        <PropertyView key={p.id} id={p.id} />
      ))}
    </div>
  );
}
