"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BlastEvent, DraftSummary, SignOff } from "@/lib/types";
import { Card, ErrorBox, PageHeader, Spinner, StatusChip, fmtDate } from "@/components/ui";

interface Overview {
  events: BlastEvent[];
  flagged_drafts: DraftSummary[];
  signoffs_needing_renewal: SignOff[];
}

export default function BlastPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Overview>("/api/blast-radius").then(setData).catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <PageHeader
        title="Blast radius"
        subtitle="When an approved fact or rule changes, every stored draft and sign-off that relied on the old version is listed for re-review. Change a fact in the Truth Ledger to see it here."
      />
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card className="p-4">
            <h2 className="mb-3 font-semibold text-slate-900">Drafts needing re-review ({data.flagged_drafts.length})</h2>
            {data.flagged_drafts.length === 0 && <p className="text-sm text-slate-500">Nothing is waiting for re-review.</p>}
            <ul className="space-y-2">
              {data.flagged_drafts.map((d) => (
                <li key={d.id} className="rounded-md border border-slate-200 p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <Link href={`/drafts/${d.id}`} className="font-medium text-indigo-700 hover:underline">{d.title}</Link>
                    <StatusChip status={d.status} />
                  </div>
                  <p className="mt-1 text-xs text-red-700">{d.rereview_reason}</p>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-4">
            <h2 className="mb-3 font-semibold text-slate-900">Sign-offs needing renewal ({data.signoffs_needing_renewal.length})</h2>
            {data.signoffs_needing_renewal.length === 0 && <p className="text-sm text-slate-500">All sign-offs are current.</p>}
            <ul className="space-y-2">
              {data.signoffs_needing_renewal.map((s) => (
                <li key={s.id} className="rounded-md border border-slate-200 p-3 text-xs">
                  <Link href={`/drafts/${s.draft_id}`} className="text-sm font-medium text-indigo-700 hover:underline">{s.draft_title}</Link>
                  <div className="mt-1 text-slate-600">
                    v{s.version_number} signed by {s.signed_by} on {fmtDate(s.signed_at)} against {s.fact_labels.join(", ")} · rulebook v{s.rulebook_version}
                  </div>
                  <div className="mt-1 text-red-700">{s.renewal_reason}</div>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-4 lg:col-span-2">
            <h2 className="mb-3 font-semibold text-slate-900">Fact changes</h2>
            {data.events.length === 0 && (
              <p className="text-sm text-slate-500">
                No fact has changed yet. Try it: <Link href="/ledger?fact=F-12" className="text-indigo-600 underline">Truth Ledger → F-12 → New version</Link> (brand admin).
              </p>
            )}
            <ul className="space-y-3">
              {data.events.map((e) => (
                <li key={e.id} className="rounded-md border border-slate-200 p-3 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <b>{e.old_fact.label}</b> ({e.old_fact.value_text}) {e.new_fact ? <>→ <b>{e.new_fact.label}</b> ({e.new_fact.value_text})</> : <span className="text-red-700">retracted</span>}
                    <span className="text-xs text-slate-500">by {e.actor} · {fmtDate(e.created_at, true)} · computed in {e.elapsed_ms} ms</span>
                  </div>
                  <div className="mt-1 text-xs text-slate-600">
                    {e.affected.drafts.length} draft(s) flagged, {e.affected.signoffs.length} sign-off(s) needing renewal
                    {e.affected.historic_versions ? `, ${e.affected.historic_versions} older version(s) also cited it` : ""}:
                    {" "}{e.affected.drafts.map((d) => d.title).join(", ") || "none"}
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}
