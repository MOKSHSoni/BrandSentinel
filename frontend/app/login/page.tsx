"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { roleLabel, useAuth } from "@/lib/auth";
import type { User } from "@/lib/types";
import { ErrorBox, Spinner } from "@/components/ui";

const WHAT_THEY_DO: Record<string, string> = {
  "priya@nimbuspay.example": "Writes drafts in-house. Sees full evidence for her own drafts.",
  "arjun@bluefin.example": "Agency writer. Sees fact IDs but not the internal documents behind them.",
  "meera@nimbuspay.example": "Reviews every draft, signs off, requests changes, overrides with a reason.",
  "rahul@nimbuspay.example": "Owns the Truth Ledger and rulebook. Changing a fact triggers blast radius.",
};

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (user) router.replace("/");
  }, [user, router]);

  useEffect(() => {
    api<User[]>("/api/auth/demo-users")
      .then(setUsers)
      .catch((e) => setError(e.message));
  }, []);

  async function enter(email: string) {
    setBusy(email);
    setError(null);
    try {
      await login(email);
      router.push("/");
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-indigo-50 to-white">
      <div className="mx-auto max-w-5xl px-4 py-14">
        <div className="mb-10 text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-xl bg-indigo-600 text-white shadow">
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2.2">
              <path d="M12 3l7 3v5c0 4.5-3 8.5-7 10-4-1.5-7-5.5-7-10V6l7-3z" />
              <path d="M9 12l2 2 4-4" />
            </svg>
          </div>
          <h1 className="text-3xl font-semibold text-slate-900">BrandSentinel</h1>
          <p className="mx-auto mt-3 max-w-2xl text-slate-600">
            Checks marketing content against a versioned store of approved facts and brand rules before it is published,
            shows the evidence behind every finding, and tells you which drafts need re-review when an approved fact changes.
          </p>
          <p className="mt-2 text-sm text-slate-500">Demo brand: <b>Nimbus Pay</b>, a fictional UPI payments app. Pick a person to continue (no password needed).</p>
        </div>
        <ErrorBox error={error} />
        {!users && !error && (
          <div className="text-center">
            <Spinner label="Waking up the server (first visit can take ~30 s)…" />
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          {users?.map((u) => (
            <button
              key={u.id}
              onClick={() => enter(u.email)}
              disabled={busy !== null}
              className="group rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-indigo-300 hover:shadow-md disabled:opacity-60"
            >
              <div className="flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-full bg-slate-800 text-sm font-semibold text-white">
                  {u.name.split(" ").map((p) => p[0]).join("")}
                </span>
                <div>
                  <div className="font-medium text-slate-900">{u.name}</div>
                  <div className="text-sm text-slate-500">{roleLabel(u)} · {u.organisation}</div>
                </div>
                <span className="ml-auto text-sm text-indigo-600 opacity-0 transition group-hover:opacity-100">
                  {busy === u.email ? "Signing in…" : "Continue →"}
                </span>
              </div>
              <p className="mt-3 text-sm text-slate-600">{WHAT_THEY_DO[u.email]}</p>
            </button>
          ))}
        </div>
        <p className="mt-8 text-center text-xs text-slate-400">Team ChaturYukti · Inkloom AI problem statement: intelligent brand governance before publication</p>
      </div>
    </div>
  );
}
