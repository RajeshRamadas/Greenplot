"use client";

import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Page, Property, User, Vendor } from "./types";

export interface Lookups {
  staff: User[];
  supervisors: User[];
  vendors: Vendor[];
  properties: Property[];
}

let cache: { key: string; value: Lookups } | null = null;

/** Option lists for assignment and property pickers, fetched once per session. */
export function useLookups(): Lookups {
  const { me, can } = useAuth();
  const [v, setV] = useState<Lookups>(cache?.value ?? { staff: [], supervisors: [], vendors: [], properties: [] });
  useEffect(() => {
    if (!me) return;
    const key = me.id;
    if (cache?.key === key) return setV(cache.value);
    (async () => {
      const safe = <T,>(p: Promise<T>, fallback: T) => p.catch(() => fallback);
      const empty = { items: [] as never[], total: 0, limit: 0, offset: 0 };
      const [staff, sups, admins, vendors, props] = await Promise.all([
        can("users.read") ? safe(api<Page<User>>("/users", { query: { role: "staff", active: true, limit: 500 } }), empty) : empty,
        can("users.read") ? safe(api<Page<User>>("/users", { query: { role: "supervisor", active: true, limit: 500 } }), empty) : empty,
        can("users.read") ? safe(api<Page<User>>("/users", { query: { role: "layout_admin", active: true, limit: 500 } }), empty) : empty,
        can("vendors.read") ? safe(api<Page<Vendor>>("/vendors", { query: { active: true, limit: 500 } }), empty) : empty,
        can("properties.read") ? safe(api<Page<Property>>("/properties", { query: { limit: 500 } }), empty) : empty,
      ]);
      const value = {
        staff: [...staff.items, ...sups.items],
        supervisors: [...sups.items, ...admins.items],
        vendors: vendors.items,
        properties: props.items,
      };
      cache = { key, value };
      setV(value);
    })();
  }, [me, can]);
  return v;
}

export function invalidateLookups() {
  cache = null;
}
