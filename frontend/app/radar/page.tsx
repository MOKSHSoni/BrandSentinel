"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Radar, RadarLink } from "@/lib/types";
import { Card, ErrorBox, PageHeader, Spinner, fmtDate } from "@/components/ui";

const PERIODS: [number, string][] = [[7, "7 days"], [30, "30 days"], [90, "90 days"], [0, "All time"]];

function href(l: RadarLink): string {
  if (l.type === "fact") return `/ledger?fact=${l.key}`;
  if (l.type === "rule") return `/rules?rule=${l.key}`;
  return `/drafts/${l.id}`;
}

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <h2 className="font-semibold text-slate-900">{title}</h2>
      <p className="mb-3 text-xs text-slate-500">{hint}</p>
      {children}
    </Card>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-500">{children}</p>;
}

export default function RadarPage() {
  const [days, setDays] = useState(30);
  const [data, setData] = useState<Radar | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    setError(null);
    api<Radar>(`/api/radar?days=${days}`).then(setData).catch((e) => setError(e.message));
  }, [days]);

  const period = days ? `the last ${days} days` : "all time";

  return (
    <div className="space-y-5">
      <PageHeader
        title="Governance Drift Radar"
        subtitle="Where brand governance is failing or creating unnecessary review work, built only from stored reviews, decisions, facts and sign-offs."
        actions={
          <div className="inline-flex rounded-md bg-slate-100 p-0.5 text-sm" role="tablist" aria-label="Period">
            {PERIODS.map(([d, label]) => (
              <button key={d} role="tab" aria-selected={days === d} onClick={() => setDays(d)}
                className={`rounded px-3 py-1 ${days === d ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-600"}`}>
                {label}
              </button>
            ))}
          </div>
        }
      />
      <ErrorBox error={error} />
      {!data && !error && <Spinner label="Building the radar…" />}
      {data && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["Versions reviewed", data.period.versions_reviewed, period],
              ["Drafts with open blocking issues", data.open_risk.blocking.length, "right now"],
              ["Sign-offs needing renewal", data.open_risk.renewals.length, "right now"],
              ["Facts expired or expiring", data.freshness.expired.length + data.freshness.expiring.length, `within ${data.freshness.horizon_days} days`],
            ].map(([label, n, sub]) => (
              <Card key={String(label)} className="p-4">
                <p className="text-2xl font-semibold text-slate-900">{n}</p>
                <p className="text-xs text-slate-600">{label}</p>
                <p className="text-[11px] text-slate-400">{sub}</p>
              </Card>
            ))}
          </div>

          <Section title="Act on these" hint="Each item links to the fact, rule or draft to fix. The radar never changes a rule or fact by itself.">
            {data.actions.length === 0 ? <Empty>Nothing needs action right now.</Empty> : (
              <ul className="space-y-1.5">
                {data.actions.map((a, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${a.severity === "high" ? "bg-red-500" : "bg-amber-500"}`} />
                    <span className="flex-1 text-slate-700">{a.text}</span>
                    <Link href={href(a.link)} className="shrink-0 text-xs font-medium text-indigo-700 hover:underline">Open →</Link>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <div className="grid gap-5 lg:grid-cols-2">
            <Section title="Open risk now" hint="Current state, not limited to the period: blocking findings, sign-offs to renew, drafts relying on facts that are no longer valid.">
              {data.open_risk.blocking.length + data.open_risk.renewals.length + data.open_risk.stale_dependencies.length === 0 ? (
                <Empty>No open risk.</Empty>
              ) : (
                <div className="space-y-3 text-sm">
                  {data.open_risk.blocking.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Open blocking findings</p>
                      <ul className="space-y-1">
                        {data.open_risk.blocking.map((b) => (
                          <li key={b.draft_id} className="flex items-center justify-between gap-2">
                            <Link href={`/drafts/${b.draft_id}`} className="text-indigo-700 hover:underline">{b.title} <span className="text-slate-400">v{b.version}</span></Link>
                            <span className="text-xs text-slate-600">{b.open_blocking} blocking{b.critical ? `, ${b.critical} critical` : ""}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {data.open_risk.renewals.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Sign-offs needing renewal</p>
                      <ul className="space-y-1">
                        {data.open_risk.renewals.map((r) => (
                          <li key={r.signoff_id}><Link href={`/drafts/${r.draft_id}`} className="text-indigo-700 hover:underline">{r.title}</Link> <span className="text-xs text-slate-500">· {r.reason}</span></li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {data.open_risk.stale_dependencies.length > 0 && (
                    <div>
                      <p className="mb-1 text-xs font-medium text-slate-500">Drafts relying on facts that are no longer valid</p>
                      <ul className="space-y-1">
                        {data.open_risk.stale_dependencies.map((s, i) => (
                          <li key={i}>
                            <Link href={`/drafts/${s.draft_id}`} className="text-indigo-700 hover:underline">{s.title}</Link>{" "}
                            <span className="text-xs text-slate-500">cites <Link href={`/ledger?fact=${s.fact_key}`} className="underline">{s.fact}</Link> ({s.problem})</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </Section>

            <Section title="Fact freshness" hint={`From each approved fact's recorded validity date, as of ${fmtDate(data.freshness.today)}.`}>
              {data.freshness.expired.length + data.freshness.expiring.length === 0 ? (
                <Empty>No approved fact expires in the next {data.freshness.horizon_days} days.</Empty>
              ) : (
                <ul className="space-y-1 text-sm">
                  {data.freshness.expired.map((f) => (
                    <li key={f.key} className="flex justify-between gap-2"><Link href={`/ledger?fact=${f.key}`} className="text-indigo-700 hover:underline">{f.label} · {f.metric}</Link><span className="text-xs font-medium text-red-700">expired {f.days} day(s) ago</span></li>
                  ))}
                  {data.freshness.expiring.map((f) => (
                    <li key={f.key} className="flex justify-between gap-2"><Link href={`/ledger?fact=${f.key}`} className="text-indigo-700 hover:underline">{f.label} · {f.metric}</Link><span className="text-xs text-amber-700">expires in {f.days} day(s)</span></li>
                  ))}
                </ul>
              )}
              {data.freshness.no_end_date.length > 0 && (
                <p className="mt-2 text-xs text-slate-500">No validity end date recorded: {data.freshness.no_end_date.map((f) => f.label).join(", ")}.</p>
              )}
            </Section>
          </div>

          <Section title={`Recurring findings · ${period}`} hint={`How many of the ${data.period.versions_reviewed} draft versions reviewed in ${period} each check fired in.`}>
            {data.recurring.length === 0 ? (
              <Empty>No draft versions were reviewed in {period}, so there is nothing to count. Choose a longer period.</Empty>
            ) : (
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr><th className="py-1.5">Check</th><th>Versions affected</th><th>Findings</th><th>Examples</th></tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.recurring.map((r) => (
                    <tr key={r.key}>
                      <td className="py-1.5 pr-2">{r.rule_key ? <Link href={`/rules?rule=${r.rule_key}`} className="text-indigo-700 hover:underline">{r.label}</Link> : r.label}</td>
                      <td className="pr-2">{r.versions_affected} of {r.versions_reviewed}</td>
                      <td className="pr-2">{r.findings}</td>
                      <td className="text-xs text-slate-500">
                        {r.examples.map((e, i) => <span key={i}>{i > 0 && " · "}<Link href={`/drafts/${e.draft_id}`} className="hover:underline">“{e.quote}”</Link></span>)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Section>

          <Section title={`Reviewer disagreement · ${period}`} hint="Decisions made in the period. Checks people often dismiss or override may be unclear or too strict; the reasons are what they recorded.">
            {data.disagreement.length === 0 ? (
              <Empty>No decisions were recorded in {period}.</Empty>
            ) : (
              <div className="space-y-3">
                {data.disagreement.map((d) => (
                  <div key={d.key} className="rounded-md border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      {d.rule_key ? <Link href={`/rules?rule=${d.rule_key}`} className="font-medium text-indigo-700 hover:underline">{d.label}</Link> : <span className="font-medium">{d.label}</span>}
                      <span className="text-xs text-slate-600">
                        {d.decided} decision(s): {d.fixed} fixed, {d.dismissed} dismissed, {d.overridden} overridden ·{" "}
                        {d.enough_data ? <b className={d.rate! >= 0.5 ? "text-red-700" : ""}>{d.disputed} of {d.decided} set aside</b> : <span className="text-slate-400">too few decisions to judge</span>}
                      </span>
                    </div>
                    {d.recommendation && <p className="mt-1 text-xs text-amber-800">{d.recommendation}</p>}
                    {d.reasons.length > 0 && (
                      <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
                        {d.reasons.map((r, i) => (
                          <li key={i}>“{r.reason}” <span className="text-slate-400">({r.status}{r.by ? ` by ${r.by}` : ""}, <Link href={`/drafts/${r.draft_id}`} className="underline">{r.title}</Link>)</span></li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>

          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            {data.notes.map((n, i) => <span key={i}>{n}</span>)}
            <span>Generated {fmtDate(data.period.until, true)}.</span>
          </div>
        </>
      )}
    </div>
  );
}
