"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { PropertyView } from "@/components/PropertyView";

export default function PropertyPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <>
      <p className="small" style={{ marginBottom: 8 }}>
        <Link href="/properties">← All properties</Link>
      </p>
      <PropertyView id={id} />
    </>
  );
}
