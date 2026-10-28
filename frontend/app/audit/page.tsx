"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { Card, ErrorBox, PageHeader, Spinner, fmtDate } from "@/components/ui";

export default function AuditPage() {
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<AuditEntry[]>("/api/audit?limit=500").then(setRows).catch((e) => setError(e.message));
  }, []);
  const shown = rows?.filter((r) => !filter || `${r.action} ${r.summary} ${r.actor}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div>
      <PageHeader
        title="Audit log"
        subtitle="Every review, decision, sign-off, override, fact and rule change, with who did it and when."
        actions={<input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter…" className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />}
      />
      <ErrorBox error={error} />
      {!shown ? <Spinner /> : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-2">When</th><th className="px-4 py-2">Who</th><th className="px-4 py-2">Action</th><th className="px-4 py-2">What happened</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((r) => (
                <tr key={r.id}>
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-500">{fmtDate(r.at, true)}</td>
                  <td className="whitespace-nowrap px-4 py-2">{r.actor}</td>
                  <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-600">{r.action}</td>
                  <td className="px-4 py-2 text-slate-700">
                    {r.summary}
                    {r.draft_id && <Link href={`/drafts/${r.draft_id}`} className="ml-2 text-xs text-indigo-600 hover:underline">open draft</Link>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
