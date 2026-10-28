"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DraftSummary } from "@/lib/types";
import DemoGuide from "@/components/DemoGuide";
import { Button, Card, ErrorBox, PageHeader, Spinner, StatusChip, TierChip, fmtDate } from "@/components/ui";

export default function Dashboard() {
  const { user } = useAuth();
  const [drafts, setDrafts] = useState<DraftSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api<DraftSummary[]>("/api/drafts")
        .then((d) => alive && setDrafts(d))
        .catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [user?.id]);

  const flagged = drafts?.filter((d) => d.needs_rereview) ?? [];
  const toSign = drafts?.filter((d) => d.status === "in_review" && d.latest_version?.review_state === "done") ?? [];

  return (
    <div>
      <DemoGuide />
      <PageHeader
        title={user?.role === "creator" ? "My drafts" : "All drafts"}
        subtitle={
          user?.role === "creator"
            ? "Upload a draft to check every claim and term against the Brand Truth Ledger before it is published."
            : "Drafts from employees and agencies. Sign off only what has been checked against current facts and rules."
        }
        actions={
          <Link href="/drafts/new">
            <Button>+ New draft</Button>
          </Link>
        }
      />
      <ErrorBox error={error} />
      {flagged.length > 0 && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <b>{flagged.length} draft{flagged.length > 1 ? "s" : ""} need re-review</b> because an approved fact or rule they relied on changed.
          {user?.role !== "creator" && (
            <Link href="/blast" className="ml-2 underline">
              See blast radius
            </Link>
          )}
        </div>
      )}
      {user?.role === "manager" && toSign.length > 0 && (
        <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-800">
          {toSign.length} reviewed draft{toSign.length > 1 ? "s are" : " is"} waiting for your decision.
        </div>
      )}
      <Card className="overflow-x-auto">
        {!drafts ? (
          <div className="p-6">
            <Spinner label="Loading drafts…" />
          </div>
        ) : drafts.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">
            No drafts yet. <Link href="/drafts/new" className="text-indigo-600 underline">Check your first draft</Link>.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2.5">Draft</th>
                <th className="px-4 py-2.5">Author</th>
                <th className="px-4 py-2.5">Version</th>
                <th className="px-4 py-2.5">Open issues</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {drafts.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link href={`/drafts/${d.id}`} className="font-medium text-slate-900 hover:text-indigo-700">
                      {d.title}
                    </Link>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-500">
                      {d.channel && <span>{d.channel}</span>}
                      <TierChip tier={d.latest_version?.effective_tier ?? d.sensitivity} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {d.created_by.name}
                    <div className="text-xs text-slate-400">{d.created_by.organisation}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">v{d.latest_version?.number}</td>
                  <td className="px-4 py-3">
                    {d.latest_version?.review_state === "pending" ? (
                      <Spinner label="reviewing" />
                    ) : (
                      <span className="flex gap-2 text-xs">
                        {(d.counts.open_blocking ?? 0) > 0 ? (
                          <span className="rounded bg-red-50 px-1.5 py-0.5 font-medium text-red-700">{d.counts.open_blocking} blocking</span>
                        ) : (
                          <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-medium text-emerald-700">0 blocking</span>
                        )}
                        <span className="text-slate-500">{d.counts.supported ?? 0} supported</span>
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col items-start gap-1">
                      <StatusChip status={d.status} />
                      {d.needs_rereview && <span className="text-xs font-medium text-red-700">Re-review needed</span>}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-500">{fmtDate(d.updated_at, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
