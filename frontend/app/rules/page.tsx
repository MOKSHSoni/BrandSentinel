"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Rule, RuleSimulation } from "@/lib/types";
import { Button, Card, ErrorBox, PageHeader, SeverityChip, Spinner, StatusChip, TierChip, fmtDate } from "@/components/ui";

interface RulesResponse {
  current_version: number;
  rules: Rule[];
  history: { version: number; note: string; created_at: string }[];
}

const KIND: Record<string, string> = {
  terminology: "Terminology",
  competitor: "Competitor terms",
  banned_phrase: "Banned phrases",
  disclaimer: "Required disclaimer",
  tone: "Tone",
  confidential_term: "Confidential terms",
  accessibility: "Image accessibility",
  palette: "Image palette",
};

const CHANGE_LABEL: Record<string, string> = {
  new: "New finding",
  removed: "Finding removed",
  now_blocking: "Would block sign-off",
  no_longer_blocking: "Would no longer block",
  severity: "Severity changes",
};

/** The list a rule matches on, whichever config key the rule kind uses. */
function listKey(rule: Rule): "terms" | "variants" | "colors" | null {
  const cfg = rule.config ?? {};
  if (Array.isArray(cfg.colors)) return "colors";
  if (Array.isArray(cfg.terms)) return "terms";
  if (Array.isArray(cfg.variants)) return "variants";
  return null;
}

function RuleEditor({ rule, onDone }: { rule: Rule; onDone: () => void }) {
  const key = listKey(rule);
  const cfg = rule.config ?? {};
  const [guideline, setGuideline] = useState(rule.guideline);
  const [severity, setSeverity] = useState(rule.severity);
  const [blocking, setBlocking] = useState(rule.blocking);
  const [status, setStatus] = useState(rule.status);
  const [list, setList] = useState(key ? ((cfg[key] as string[]) ?? []).join(", ") : "");
  const [minContrast, setMinContrast] = useState(String(cfg.min_contrast ?? ""));
  const [minLarge, setMinLarge] = useState(String(cfg.min_contrast_large ?? ""));
  const [note, setNote] = useState("");
  const [sim, setSim] = useState<RuleSimulation | null>(null);
  const [busy, setBusy] = useState<"sim" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  function body() {
    const config: Record<string, unknown> = { ...cfg };
    if (key) config[key] = list.split(",").map((s) => s.trim()).filter(Boolean);
    if (rule.kind === "accessibility") {
      config.min_contrast = Number(minContrast);
      config.min_contrast_large = Number(minLarge);
    }
    return { guideline, severity, blocking, status, config, note };
  }
  const touch = <T,>(setter: (v: T) => void, v: T) => { setter(v); setSim(null); };

  async function run(kind: "sim" | "save") {
    setBusy(kind);
    setError(null);
    try {
      if (kind === "sim") setSim(await api<RuleSimulation>(`/api/rules/${rule.id}/simulate`, { method: "POST", json: body() }));
      else {
        await api(`/api/rules/${rule.id}`, { method: "PUT", json: body() });
        onDone();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-md border border-indigo-200 bg-indigo-50/40 p-3 text-sm">
      <label className="block">
        <span className="text-slate-600">Guideline (quoted in every finding)</span>
        <textarea value={guideline} onChange={(e) => touch(setGuideline, e.target.value)} rows={2} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
      </label>
      {key && (
        <label className="block">
          <span className="text-slate-600">{key === "colors" ? "Palette colours (hex, comma-separated)" : key === "terms" ? "Terms (comma-separated)" : "Wrong variants (comma-separated)"}</span>
          <input value={list} onChange={(e) => touch(setList, e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
        </label>
      )}
      {rule.kind === "accessibility" && (
        <div className="flex flex-wrap gap-4">
          <label>Min. contrast <input type="number" step="0.1" value={minContrast} onChange={(e) => touch(setMinContrast, e.target.value)} className="ml-1 w-20 rounded-md border border-slate-300 bg-white px-2 py-1" /></label>
          <label>Large text <input type="number" step="0.1" value={minLarge} onChange={(e) => touch(setMinLarge, e.target.value)} className="ml-1 w-20 rounded-md border border-slate-300 bg-white px-2 py-1" /></label>
        </div>
      )}
      <div className="flex flex-wrap gap-4">
        <label>
          Severity{" "}
          <select value={severity} onChange={(e) => touch(setSeverity, e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1">
            {["critical", "major", "minor"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={blocking} onChange={(e) => touch(setBlocking, e.target.checked)} /> Blocks sign-off
        </label>
        <label>
          Status{" "}
          <select value={status} onChange={(e) => touch(setStatus, e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1">
            <option>active</option>
            <option>retired</option>
          </select>
        </label>
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Change note" className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={busy !== null} onClick={() => run("sim")}>{busy === "sim" ? "Simulating…" : "Preview impact"}</Button>
        <Button disabled={busy !== null || !sim} onClick={() => run("save")} title={sim ? "" : "Preview the impact first"}>
          {busy === "save" ? "Saving…" : "Save as a new rulebook version"}
        </Button>
      </div>
      {sim && (
        <div className="rounded-md bg-white p-3 ring-1 ring-indigo-200">
          <p className="mb-1">
            <span className="mr-2 rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-indigo-800">Simulation · not applied</span>
            {sim.rule.key} v{sim.rule.from_version} → v{sim.rule.to_version}:{" "}
            {sim.totals.new} new finding(s), {sim.totals.removed} removed, {sim.totals.now_blocking} newly blocking, {sim.totals.no_longer_blocking} no longer blocking
            across {sim.drafts.length} draft(s). <span className="text-xs text-slate-400">{sim.elapsed_ms} ms</span>
          </p>
          <p className="text-xs text-amber-800">
            Saving creates a new rulebook version: {sim.signoffs_to_renew.length} valid sign-off(s) were made under the current rulebook and would need renewal
            {sim.signoffs_to_renew.length ? ` (${sim.signoffs_to_renew.map((s) => s.draft_title).join(", ")})` : ""}.
          </p>
          {sim.drafts.length === 0 && <p className="mt-1 text-xs text-slate-500">No stored draft would get a different finding from this rule.</p>}
          <ul className="mt-2 space-y-1.5 text-xs">
            {sim.drafts.map((d) => (
              <li key={d.draft_id}>
                <Link href={`/drafts/${d.draft_id}`} className="font-medium text-indigo-700 hover:underline">{d.title}</Link> <span className="text-slate-400">v{d.version}</span>
                <ul className="ml-3 list-inside list-disc text-slate-600">
                  {d.changes.map((c, i) => <li key={i}>{CHANGE_LABEL[c.change] ?? c.change}: “{c.quote}”{c.was ? ` (${c.was} → ${c.severity})` : ""}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function RulesInner() {
  const { user } = useAuth();
  const params = useSearchParams();
  const focus = params.get("rule");
  const [data, setData] = useState<RulesResponse | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<RulesResponse>("/api/rules").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (focus && data) document.getElementById(`rule-${focus}`)?.scrollIntoView({ block: "center" });
  }, [focus, data]);
  const isAdmin = user?.role === "admin";

  return (
    <div>
      <PageHeader title="Rulebook" subtitle="Deterministic checks run before any AI. Each finding cites the rule and quotes its guideline. Preview a change's impact before saving it." />
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
          <div className="space-y-2">
            {data.rules.map((r) => (
              <Card key={r.id} className={`p-4 ${focus === r.key ? "ring-2 ring-indigo-300" : ""}`}>
                <div id={`rule-${r.key}`} className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-indigo-700">{r.key}</span>
                  <span className="font-medium text-slate-900">{r.name}</span>
                  <span className="text-xs text-slate-500">{KIND[r.kind] ?? r.kind} · v{r.version}</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    <SeverityChip severity={r.severity} />
                    {r.blocking ? <span className="text-xs text-red-600">blocking</span> : <span className="text-xs text-slate-400">suggestion</span>}
                    {isAdmin ? (
                      <select
                        aria-label={`Sensitivity of ${r.key}`}
                        value={r.sensitivity}
                        onChange={async (e) => {
                          try {
                            await api(`/api/rules/${r.id}/sensitivity`, { method: "PATCH", json: { sensitivity: e.target.value } });
                            load();
                          } catch (err) {
                            setError((err as Error).message);
                          }
                        }}
                        title="Reclassify (does not create a new rulebook version)"
                        className="rounded border border-slate-300 bg-white px-1 py-0.5 text-[11px] capitalize"
                      >
                        {["public", "internal", "confidential", "restricted"].map((t) => <option key={t} value={t}>{t}</option>)}
                      </select>
                    ) : (
                      <TierChip tier={r.sensitivity} />
                    )}
                    <StatusChip status={r.status} />
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{r.guideline}</p>
                {r.config && listKey(r) ? (
                  <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-slate-500">
                    {r.config.correct ? <>Correct form: <b>{String(r.config.correct)}</b>.</> : null}
                    {listKey(r) === "colors"
                      ? (r.config.colors as string[]).map((c) => (
                          <span key={c} className="inline-flex items-center gap-1 rounded bg-white px-1 ring-1 ring-slate-200">
                            <span className="inline-block h-3 w-3 rounded-sm ring-1 ring-slate-300" style={{ background: c }} />{c}
                          </span>
                        ))
                      : ((r.config[listKey(r)!] as string[]) ?? []).length > 0 && <>Matches: {(r.config[listKey(r)!] as string[]).join(", ")}</>}
                  </p>
                ) : r.config?.min_contrast ? (
                  <p className="mt-1 text-xs text-slate-500">Contrast at least {String(r.config.min_contrast)}:1 ({String(r.config.min_contrast_large)}:1 for large text); alt text required.</p>
                ) : null}
                {isAdmin && (
                  <div className="mt-2">
                    <Button variant="ghost" className="text-xs" onClick={() => setEditing(editing === r.id ? null : r.id)}>{editing === r.id ? "Close" : "Edit rule"}</Button>
                    {editing === r.id && <RuleEditor rule={r} onDone={() => { setEditing(null); load(); }} />}
                  </div>
                )}
              </Card>
            ))}
          </div>
          <Card className="h-fit p-4">
            <h2 className="mb-2 text-sm font-semibold text-slate-700">Rulebook versions</h2>
            <p className="mb-3 text-2xl font-semibold">v{data.current_version}</p>
            <ul className="space-y-2 text-xs">
              {data.history.map((h) => (
                <li key={h.version}>
                  <b>v{h.version}</b> · {fmtDate(h.created_at, true)}
                  <div className="text-slate-500">{h.note}</div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}

export default function RulesPage() {
  return (
    <Suspense>
      <RulesInner />
    </Suspense>
  );
}
