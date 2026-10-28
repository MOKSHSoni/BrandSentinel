"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { roleLabel, useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
import { Spinner } from "./ui";

interface Health {
  local_model: { available: boolean; model: string };
  external_model: { configured: boolean; model: string | null };
}

const NAV = [
  { href: "/", label: "Drafts", roles: ["creator", "manager", "admin"] },
  { href: "/ledger", label: "Truth Ledger", roles: ["creator", "manager", "admin"] },
  { href: "/rules", label: "Rulebook", roles: ["creator", "manager", "admin"] },
  { href: "/blast", label: "Blast radius", roles: ["manager", "admin"] },
  { href: "/audit", label: "Audit log", roles: ["manager", "admin"] },
  { href: "/insights", label: "Insights", roles: ["manager", "admin"] },
];

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2 font-semibold text-slate-900">
      <span className="grid h-7 w-7 place-items-center rounded-md bg-indigo-600 text-white">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2.4">
          <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z" />
          <path d="M9 12l2 2 4-4" />
        </svg>
      </span>
      BrandSentinel
    </Link>
  );
}

export function UserSwitcher() {
  const { user, login, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  useEffect(() => {
    if (open && users.length === 0) api<User[]>("/api/auth/demo-users").then(setUsers).catch(() => {});
  }, [open, users.length]);
  if (!user) return null;
  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-slate-100">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-slate-800 text-xs font-semibold text-white">
          {user.name.split(" ").map((p) => p[0]).join("")}
        </span>
        <span className="hidden text-xs leading-tight sm:block">
          <span className="block font-medium text-slate-900">{user.name}</span>
          <span className="text-slate-500">{roleLabel(user)} · {user.organisation}</span>
        </span>
        <span className="text-slate-400">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-1 w-72 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">Switch demo user</p>
          {users.map((u) => (
            <button
              key={u.id}
              onClick={async () => {
                setOpen(false);
                await login(u.email);
                router.push("/");
              }}
              className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-slate-50 ${u.id === user.id ? "bg-indigo-50" : ""}`}
            >
              <span>
                <span className="block font-medium text-slate-900">{u.name}</span>
                <span className="text-xs text-slate-500">{roleLabel(u)} · {u.organisation}</span>
              </span>
              {u.id === user.id && <span className="text-xs text-indigo-600">current</span>}
            </button>
          ))}
          <div className="my-1 border-t border-slate-100" />
          <button
            onClick={() => {
              logout();
              router.push("/login");
            }}
            className="w-full rounded-md px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function ModelBadge() {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    api<Health>("/api/health").then(setH).catch(() => {});
  }, []);
  if (!h) return null;
  const label = h.local_model.available
    ? `AI judge: local ${h.local_model.model.split(":")[0]}`
    : h.external_model.configured
      ? `AI judge: external ${h.external_model.model} (public tier only)`
      : "AI judge off: rules only";
  const tone = h.local_model.available ? "bg-indigo-50 text-indigo-700" : h.external_model.configured ? "bg-fuchsia-50 text-fuchsia-700" : "bg-slate-100 text-slate-600";
  return <span className={`hidden rounded-full px-2.5 py-1 text-xs font-medium lg:inline ${tone}`}>{label}</span>;
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (ready && !user && pathname !== "/login") router.replace("/login");
  }, [ready, user, pathname, router]);

  if (pathname === "/login") return <>{children}</>;
  if (!ready || !user) {
    return (
      <div className="grid min-h-screen place-items-center">
        <Spinner label="Loading…" />
      </div>
    );
  }
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
          <Logo />
          <nav className="flex flex-1 gap-1 overflow-x-auto">
            {NAV.filter((n) => n.roles.includes(user.role)).map((n) => {
              const active = n.href === "/" ? pathname === "/" || pathname.startsWith("/drafts") : pathname.startsWith(n.href);
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm ${active ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-50"}`}
                >
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <ModelBadge />
          <UserSwitcher />
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      <footer className="mx-auto max-w-7xl px-4 pb-8 text-xs text-slate-400">
        BrandSentinel · Team ChaturYukti · Demo brand “Nimbus Pay” is fictional. The AI recommends; people accept fixes and sign off.
      </footer>
    </div>
  );
}
