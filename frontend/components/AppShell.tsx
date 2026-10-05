"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/Icon";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { roleLabel } from "@/lib/format";
import { useOnline } from "@/lib/hooks";
import { listQueue, onQueueChange, startSyncLoop } from "@/lib/offline";
import type { Role } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: string;
  group?: string;
  short?: string;
}

const NAV: Record<Role, NavItem[]> = {
  layout_admin: [
    { href: "/dashboard", label: "Dashboard", icon: "home" },
    { href: "/tickets", label: "Service tickets", short: "Tickets", icon: "ticket", group: "Operations" },
    { href: "/maintenance", label: "Maintenance", icon: "wrench", group: "Operations" },
    { href: "/approvals", label: "Pending approvals", icon: "check", group: "Operations" },
    { href: "/gardening", label: "Gardening & cleaning", icon: "leaf", group: "Operations" },
    { href: "/inspections", label: "Property Watch", icon: "eye", group: "Operations" },
    { href: "/complaints", label: "Complaints", icon: "message", group: "Operations" },
    { href: "/properties", label: "Properties & residents", icon: "building", group: "Layout" },
    { href: "/assets", label: "Assets", icon: "box", group: "Layout" },
    { href: "/staff", label: "Staff", icon: "users", group: "Layout" },
    { href: "/vendors", label: "Vendors", icon: "truck", group: "Layout" },
    { href: "/visitors", label: "Visitors", icon: "users", group: "Security" },
    { href: "/vehicles", label: "Vehicles", icon: "car", group: "Security" },
    { href: "/patrol", label: "Patrol", icon: "route", group: "Security" },
    { href: "/incidents", label: "Incidents & SOS", icon: "alert", group: "Security" },
    { href: "/billing", label: "Billing & dues", icon: "rupee", group: "Finance" },
    { href: "/notices", label: "Announcements", icon: "bell", group: "Communication" },
    { href: "/records", label: "Digital records", icon: "search", group: "Records" },
    { href: "/reports", label: "Reports", icon: "chart", group: "Records" },
    { href: "/audit", label: "Audit log", icon: "list", group: "Records" },
    { href: "/settings", label: "Settings", icon: "settings", group: "Admin" },
  ],
  supervisor: [
    { href: "/dashboard", label: "Dashboard", icon: "home" },
    { href: "/tickets", label: "Service tickets", short: "Tickets", icon: "ticket", group: "Review" },
    { href: "/approvals", label: "Pending approvals", icon: "check", group: "Review" },
    { href: "/maintenance", label: "Maintenance", icon: "wrench", group: "Review" },
    { href: "/gardening", label: "Gardening & cleaning", icon: "leaf", group: "Review" },
    { href: "/inspections", label: "Property Watch", icon: "eye", group: "Review" },
    { href: "/complaints", label: "Complaints", icon: "message", group: "Review" },
    { href: "/my-tasks", label: "My tasks", icon: "clipboard", group: "Field" },
    { href: "/scan", label: "Scan asset", icon: "qr", group: "Field" },
    { href: "/assets", label: "Assets", icon: "box", group: "Layout" },
    { href: "/staff", label: "Staff", icon: "users", group: "Layout" },
    { href: "/vendors", label: "Vendors", icon: "truck", group: "Layout" },
    { href: "/incidents", label: "Incidents & SOS", icon: "alert", group: "Security" },
    { href: "/records", label: "Digital records", icon: "search", group: "Records" },
    { href: "/reports", label: "Reports", icon: "chart", group: "Records" },
  ],
  staff: [
    { href: "/my-tasks", label: "My tasks", icon: "clipboard" },
    { href: "/tickets", label: "Service tickets", short: "Tickets", icon: "ticket" },
    { href: "/scan", label: "Scan asset", icon: "qr" },
    { href: "/attendance", label: "Attendance", icon: "user" },
    { href: "/complaints", label: "Complaints", icon: "message" },
    { href: "/records", label: "Records", icon: "search" },
    { href: "/offline", label: "Offline queue", icon: "sync" },
  ],
  vendor: [
    { href: "/tickets", label: "Service tickets", short: "Tickets", icon: "ticket" },
    { href: "/my-tasks", label: "My jobs", icon: "clipboard" },
    { href: "/scan", label: "Scan asset", icon: "qr" },
    { href: "/maintenance", label: "Job history", icon: "wrench" },
    { href: "/offline", label: "Offline queue", icon: "sync" },
  ],
  guard: [
    { href: "/dashboard", label: "Gate", icon: "home" },
    { href: "/visitors", label: "Visitors", icon: "users" },
    { href: "/vehicles", label: "Vehicles", icon: "car" },
    { href: "/patrol", label: "Patrol", icon: "route" },
    { href: "/incidents", label: "Incidents & SOS", icon: "alert" },
    { href: "/attendance", label: "Attendance", icon: "user" },
    { href: "/offline", label: "Offline queue", icon: "sync" },
  ],
  resident: [
    { href: "/dashboard", label: "Home", icon: "home" },
    { href: "/tickets", label: "Service tickets", short: "Tickets", icon: "ticket" },
    { href: "/my-property", label: "My property", icon: "building" },
    { href: "/inspections", label: "Property Watch", icon: "eye" },
    { href: "/maintenance", label: "Maintenance history", icon: "wrench" },
    { href: "/visitors", label: "Visitors", icon: "users" },
    { href: "/vehicles", label: "Vehicles", icon: "car" },
    { href: "/billing", label: "Dues & payments", icon: "rupee" },
    { href: "/notices", label: "Notices", icon: "bell" },
    { href: "/sos", label: "SOS", icon: "sos" },
  ],
  super_admin: [{ href: "/tenants", label: "Tenants", icon: "layers" }],
};

const BOTTOM: Partial<Record<Role, string[]>> = {
  staff: ["/my-tasks", "/scan", "/attendance", "/offline"],
  vendor: ["/tickets", "/my-tasks", "/scan", "/offline"],
  guard: ["/dashboard", "/visitors", "/patrol", "/incidents"],
  resident: ["/dashboard", "/tickets", "/maintenance", "/billing", "/sos"],
  supervisor: ["/dashboard", "/tickets", "/approvals", "/maintenance"],
  layout_admin: ["/dashboard", "/tickets", "/maintenance", "/approvals"],
};

export function homeFor(role?: Role) {
  if (!role) return "/login";
  return NAV[role][0].href;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { me, loading, logout } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const online = useOnline();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    if (!loading && !me) router.replace(`/login?next=${encodeURIComponent(path)}`);
  }, [loading, me, router, path]);

  useEffect(() => setOpen(false), [path]);

  useEffect(() => {
    if (!me) return;
    startSyncLoop();
    const refreshQueue = () => listQueue().then(({ ops, blobs }) => setPending([...ops, ...blobs].filter((x) => x.state !== "synced").length)).catch(() => {});
    refreshQueue();
    const off = onQueueChange(refreshQueue);
    if (!me.tenant_id) return () => void off();
    const poll = () => online && api<{ count: number }>("/notifications/unread-count").then((r) => setUnread(r.count)).catch(() => {});
    poll();
    const t = setInterval(poll, 30_000);
    return () => {
      off();
      clearInterval(t);
    };
  }, [me, online]);

  if (loading || !me) return <div className="auth-page"><span className="muted">Loading GreenPlot…</span></div>;

  const items = NAV[me.role];
  const groups: (string | undefined)[] = [];
  items.forEach((i) => !groups.includes(i.group) && groups.push(i.group));
  const isActive = (href: string) => path === href || path.startsWith(href + "/");
  const bottom = (BOTTOM[me.role] || []).map((h) => items.find((i) => i.href === h)).filter(Boolean) as NavItem[];

  return (
    <div className="shell">
      {open ? <div className="scrim" onClick={() => setOpen(false)} /> : null}
      <aside className={`sidebar ${open ? "open" : ""}`} aria-label="Main navigation">
        <Link href={homeFor(me.role)} className="brand" style={{ color: "inherit", textDecoration: "none" }}>
          <b>
            <span>Green</span>Plot
          </b>
          <small>{me.tenant_name || "Platform administration"}</small>
        </Link>
        {groups.map((g) => (
          <div key={g || "main"}>
            {g ? <div className="navgroup">{g}</div> : null}
            {items
              .filter((i) => i.group === g)
              .map((i) => (
                <Link key={i.href} href={i.href} className={`navlink ${isActive(i.href) ? "active" : ""}`}>
                  <Icon name={i.icon} />
                  {i.label}
                  {i.href === "/offline" && pending ? <span className="count">{pending}</span> : null}
                </Link>
              ))}
          </div>
        ))}
        <div className="navgroup">Account</div>
        {me.tenant_id ? (
          <Link href="/notifications" className={`navlink ${isActive("/notifications") ? "active" : ""}`}>
            <Icon name="bell" /> Notifications {unread ? <span className="count">{unread}</span> : null}
          </Link>
        ) : null}
        <Link href="/profile" className={`navlink ${isActive("/profile") ? "active" : ""}`}>
          <Icon name="user" /> Profile
        </Link>
        <button className="navlink btn ghost" style={{ justifyContent: "flex-start" }} onClick={() => logout().then(() => router.replace("/login"))}>
          <Icon name="logout" /> Sign out
        </button>
      </aside>
      <div className="main">
        {!online ? <div className="offline-banner">You are offline. Work is saved on this device and syncs automatically.</div> : null}
        <header className="topbar">
          <div className="row">
            <button className="btn ghost small menu-btn" aria-label="Open menu" onClick={() => setOpen(true)}>
              <Icon name="menu" />
            </button>
            <span className="small muted">{roleLabel[me.role]}</span>
          </div>
          <div className="who">
            {pending ? (
              <Link href="/offline" className="badge amber">
                {pending} to sync
              </Link>
            ) : null}
            {me.tenant_id ? (
              <Link href="/notifications" className="btn ghost small" aria-label={`${unread} unread notifications`}>
                <Icon name="bell" />
                {unread ? <span className="badge red">{unread}</span> : null}
              </Link>
            ) : null}
            <span>{me.full_name}</span>
          </div>
        </header>
        <main className="content">{children}</main>
        {bottom.length ? (
          <nav className="bottomnav" aria-label="Quick navigation">
            {bottom.map((i) => (
              <Link key={i.href} href={i.href} className={isActive(i.href) ? "active" : ""}>
                <Icon name={i.icon} size={22} />
                {i.short ?? i.label.split(" ")[0]}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
    </div>
  );
}
