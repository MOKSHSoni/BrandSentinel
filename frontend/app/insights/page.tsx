"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, ErrorBox, PageHeader, Spinner, TierChip, fmtDate } from "@/components/ui";

interface Recurring {
  label: string;
  total: number;
  open: number;
  accepted: number;
  edited: number;
  dismissed: number;
  overridden: number;
  disagreement_rate: number | null;
}
interface PR { tp: number; fp: number; fn: number; precision: number | null; recall: number | null; target?: Record<string, number>; meets_target?: boolean | null }
interface EvalResult {
  at: string;
  mode: string;
  drafts: number;
  parts: Record<string, number>;
  seconds: number;
  categories: Record<string, PR>;
  severity: Record<string, PR>;
  evidence: { correct: number; total: number };
  problem_claims_flagged: { caught: number; total: number };
  false_alarms_per_clean_draft: number | null;
  clean_drafts: number;
  flagged_for_admin: string[];
  misses: { id: string; cat: string; quote: string }[];
  corrections?: { proposed: number; passed_all_checks: number };
}
interface Insights {
  recurring: Recurring[];
  model_calls: { id: number; at: string; purpose: string; location: string; model: string; tier: string; masked: string[]; ok: boolean; error: string; latency_ms: number }[];
}

const MODE_LABEL: Record<string, string> = {
  pipeline_rules: "BrandSentinel (rules only)",
  pipeline_ai: "BrandSentinel (rules + local AI judge)",
  llm_brand_guide: "Baseline: LLM given the brand guide",
  llm_structured_facts: "Baseline: LLM given the structured facts",
};

function count(p: PR | undefined, metric: "precision" | "recall") {
  if (!p) return "—";
  const [num, den] = metric === "recall" ? [p.tp, p.tp + p.fn] : [p.tp, p.tp + p.fp];
  return den ? `${num}/${den}` : "—";
}

export default function InsightsPage() {
  const { user } = useAuth();
  const [data, setData] = useState<Insights | null>(null);
  const [evals, setEvals] = useState<Record<string, EvalResult> | null>(null);
  const [tiers, setTiers] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = user?.role === "admin";

  const load = useCallback(() => {
    api<Insights>("/api/insights").then(setData).catch((e) => setError(e.message));
    api<Record<string, EvalResult>>("/api/eval").then(setEvals).catch(() => setEvals({}));
    api<{ external_tiers: string[] }>("/api/settings").then((s) => setTiers(s.external_tiers)).catch(() => {});
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    setError(null);
    try {
      await fn();
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const modes = evals ? Object.keys(MODE_LABEL).filter((m) => evals[m]) : [];
  const main = evals?.pipeline_ai ?? evals?.pipeline_rules;

  return (
    <div className="space-y-6">
      <PageHeader title="Insights" subtitle="Measured reliability, recurring issues and the model call log." />
      <ErrorBox error={error} />

      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold text-slate-900">Measured reliability</h2>
            <p className="text-sm text-slate-500">
              Labelled Nimbus Pay test set{main ? ` of ${main.drafts} drafts (${Object.entries(main.parts).map(([k, v]) => `${v} ${k.replace("_", "-")}`).join(", ")})` : ""}. Results are counts against the targets in our plan; targets are goals, not claims.
            </p>
          </div>
          {isAdmin && (
            <Button variant="secondary" disabled={busy !== null} onClick={() => run("eval", () => api("/api/eval/run", { method: "POST" }))}>
              {busy === "eval" ? "Running…" : "Re-run (rules only)"}
            </Button>
          )}
        </div>
        {!evals ? <Spinner /> : modes.length === 0 ? (
          <p className="text-sm text-slate-500">No evaluation stored yet.{isAdmin ? " Click “Re-run”." : ""}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="py-2 pr-4">System</th>
                  <th className="pr-4">Critical recall<br /><span className="normal-case">target ≥ 0.95</span></th>
                  <th className="pr-4">Major precision / recall<br /><span className="normal-case">target ≥ 0.90</span></th>
                  <th className="pr-4">Minor precision</th>
                  <th className="pr-4">Correct citation</th>
                  <th className="pr-4">False alarms per clean draft</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {modes.map((m) => {
                  const r = evals[m];
                  const s = r.severity;
                  return (
                    <tr key={m}>
                      <td className="py-2 pr-4 font-medium text-slate-900">{MODE_LABEL[m]}</td>
                      <td className={`pr-4 ${s.critical?.meets_target ? "text-emerald-700" : "text-red-700"}`}>{count(s.critical, "recall")} ({s.critical?.recall ?? "—"})</td>
                      <td className={`pr-4 ${s.major?.meets_target ? "text-emerald-700" : "text-red-700"}`}>
                        {count(s.major, "precision")} / {count(s.major, "recall")}
                      </td>
                      <td className="pr-4">{count(s.minor, "precision")}</td>
                      <td className="pr-4">{r.evidence.correct}/{r.evidence.total}</td>
                      <td className="pr-4">{r.false_alarms_per_clean_draft ?? "—"}</td>
                      <td className="text-xs text-slate-500">{fmtDate(r.at, true)} · {r.seconds}s</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {main && (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-slate-700">Per check ({MODE_LABEL[main.mode]})</h3>
                  <table className="w-full text-xs">
                    <thead className="text-left text-slate-500"><tr><th className="py-1">Check</th><th>Caught</th><th>Precision</th></tr></thead>
                    <tbody>
                      {Object.entries(main.categories).map(([c, v]) => (
                        <tr key={c} className={main.flagged_for_admin.includes(c) ? "text-red-700" : ""}>
                          <td className="py-0.5">{c.replace("claim_", "claim: ").replace("_", " ")}</td>
                          <td>{v.tp} of {v.tp + v.fn}</td>
                          <td>{v.tp} of {v.tp + v.fp}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {main.corrections && (
                    <p className="mt-2 text-xs text-slate-600">Corrections: {main.corrections.passed_all_checks} of {main.corrections.proposed} candidate fixes passed the three-way check and were shown.</p>
                  )}
                </div>
                <div>
                  <h3 className="mb-1 text-sm font-semibold text-slate-700">Flagged for the brand admin</h3>
                  {main.flagged_for_admin.length === 0 ? <p className="text-xs text-slate-500">No check misses its target on this set.</p> : (
                    <p className="text-xs text-red-700">Below target: {main.flagged_for_admin.join(", ")}</p>
                  )}
                  <h3 className="mb-1 mt-3 text-sm font-semibold text-slate-700">Misses</h3>
                  <ul className="space-y-0.5 text-xs text-slate-600">
                    {main.misses.map((m, i) => <li key={i}>{m.id}: {m.cat} “{m.quote}”</li>)}
                    {main.misses.length === 0 && <li>None.</li>}
                  </ul>
                </div>
              </div>
            )}
            <p className="mt-3 text-xs text-slate-400">The manual-checklist baseline is timed by people and reported separately. Small, synthetic test set: supports a first demonstration, not general performance claims.</p>
          </div>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Recurring issues</h2>
        <p className="mb-3 text-sm text-slate-500">Which checks fire most, and which ones reviewers dismiss or override (a sign that a rule is unclear).</p>
        {!data ? <Spinner /> : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="py-2">Check</th><th>Total</th><th>Open</th><th>Fixed</th><th>Dismissed</th><th>Overridden</th><th>Disagreement</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.recurring.map((r) => (
                <tr key={r.label}>
                  <td className="py-1.5">{r.label}</td>
                  <td>{r.total}</td>
                  <td>{r.open}</td>
                  <td>{r.accepted + r.edited}</td>
                  <td>{r.dismissed}</td>
                  <td>{r.overridden}</td>
                  <td className={r.disagreement_rate && r.disagreement_rate >= 0.5 ? "font-medium text-red-700" : ""}>{r.disagreement_rate == null ? "—" : `${Math.round(r.disagreement_rate * 100)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-1 font-semibold text-slate-900">Confidentiality Gateway: model call log</h2>
        <p className="mb-3 text-sm text-slate-500">
          Each request takes the highest sensitivity of anything it contains. Public content may use an approved external model; internal and confidential content stays local unless the admin approves that tier (with masking); restricted content is local only.
        </p>
        {isAdmin && (
          <div className="mb-4 flex flex-wrap items-center gap-4 rounded-md bg-slate-50 p-3 text-sm">
            <span className="font-medium text-slate-700">Admin approval for external models:</span>
            {["internal", "confidential"].map((t) => (
              <label key={t} className="flex items-center gap-1.5 capitalize">
                <input
                  type="checkbox"
                  checked={tiers.includes(t)}
                  onChange={(e) => {
                    const next = e.target.checked ? [...tiers, t] : tiers.filter((x) => x !== t);
                    run("tiers", () => api("/api/settings", { method: "PUT", json: { external_tiers: next } }));
                  }}
                />
                {t} (masked)
              </label>
            ))}
            <span className="text-xs text-slate-500">Restricted is never sent out.</span>
          </div>
        )}
        {!data ? <Spinner /> : data.model_calls.length === 0 ? <p className="text-sm text-slate-500">No model calls yet.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-slate-500"><tr><th className="py-1">When</th><th>Purpose</th><th>Route</th><th>Tier</th><th>Model</th><th>Masked</th><th>Result</th><th>Latency</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.model_calls.map((c) => (
                  <tr key={c.id}>
                    <td className="py-1">{fmtDate(c.at, true)}</td>
                    <td>{c.purpose}</td>
                    <td className={c.location === "blocked" ? "font-medium text-red-700" : c.location === "external" ? "text-fuchsia-700" : "text-indigo-700"}>{c.location}</td>
                    <td><TierChip tier={c.tier} /></td>
                    <td>{c.model}</td>
                    <td>{c.masked.length ? c.masked.join(", ") : "—"}</td>
                    <td className={c.ok ? "" : "text-red-700"}>{c.ok ? (c.location === "blocked" ? c.error : "ok") : c.error.slice(0, 80)}</td>
                    <td>{c.latency_ms ? `${(c.latency_ms / 1000).toFixed(1)} s` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {isAdmin && (
        <Card className="border-red-200 p-5">
          <h2 className="font-semibold text-slate-900">Reset demo data</h2>
          <p className="mb-3 text-sm text-slate-500">Restores the seeded Nimbus Pay ledger, rulebook and three stored drafts. Everyone&rsquo;s changes are removed.</p>
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              if (confirm("Reset all demo data?")) run("reset", () => api("/api/admin/reset", { method: "POST" }).then(() => (window.location.href = "/login")));
            }}
          >
            {busy === "reset" ? "Resetting…" : "Reset demo"}
          </Button>
        </Card>
      )}
    </div>
  );
}
