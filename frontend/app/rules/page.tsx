"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Rule } from "@/lib/types";
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
};

function RuleEditor({ rule, onDone }: { rule: Rule; onDone: () => void }) {
  const terms = (rule.config?.terms as string[] | undefined) ?? (rule.config?.variants as string[] | undefined);
  const termKey = rule.config?.terms ? "terms" : rule.config?.variants ? "variants" : null;
  const [guideline, setGuideline] = useState(rule.guideline);
  const [severity, setSeverity] = useState(rule.severity);
  const [blocking, setBlocking] = useState(rule.blocking);
  const [status, setStatus] = useState(rule.status);
  const [termText, setTermText] = useState(terms?.join(", ") ?? "");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    const config = termKey ? { ...rule.config, [termKey]: termText.split(",").map((s) => s.trim()).filter(Boolean) } : undefined;
    try {
      await api(`/api/rules/${rule.id}`, { method: "PUT", json: { guideline, severity, blocking, status, config, note } });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-md border border-indigo-200 bg-indigo-50/40 p-3 text-sm">
      <label className="block">
        <span className="text-slate-600">Guideline (quoted in every finding)</span>
        <textarea value={guideline} onChange={(e) => setGuideline(e.target.value)} rows={2} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
      </label>
      {termKey && (
        <label className="block">
          <span className="text-slate-600">{termKey === "terms" ? "Terms" : "Wrong variants"} (comma-separated)</span>
          <input value={termText} onChange={(e) => setTermText(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
        </label>
      )}
      <div className="flex flex-wrap gap-4">
        <label>
          Severity{" "}
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1">
            {["critical", "major", "minor"].map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={blocking} onChange={(e) => setBlocking(e.target.checked)} /> Blocks sign-off
        </label>
        <label>
          Status{" "}
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1">
            <option>active</option>
            <option>retired</option>
          </select>
        </label>
      </div>
      <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Change note" className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
      <p className="text-xs text-amber-800">Saving creates a new rulebook version. Existing sign-offs were checked against the old rulebook, so they will need renewal.</p>
      <ErrorBox error={error} />
      <Button onClick={save}>Save as new rulebook version</Button>
    </div>
  );
}

export default function RulesPage() {
  const { user } = useAuth();
  const [data, setData] = useState<RulesResponse | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => api<RulesResponse>("/api/rules").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader title="Rulebook" subtitle="Deterministic checks run before any AI. Each finding cites the rule and quotes its guideline." />
      <ErrorBox error={error} />
      {!data ? <Spinner /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_280px]">
          <div className="space-y-2">
            {data.rules.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-indigo-700">{r.key}</span>
                  <span className="font-medium text-slate-900">{r.name}</span>
                  <span className="text-xs text-slate-500">{KIND[r.kind] ?? r.kind} · v{r.version}</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    <SeverityChip severity={r.severity} />
                    {r.blocking ? <span className="text-xs text-red-600">blocking</span> : <span className="text-xs text-slate-400">suggestion</span>}
                    <TierChip tier={r.sensitivity} />
                    <StatusChip status={r.status} />
                  </span>
                </div>
                <p className="mt-2 text-sm text-slate-600">{r.guideline}</p>
                {r.config && (r.config.terms || r.config.variants || r.config.correct) ? (
                  <p className="mt-1 text-xs text-slate-500">
                    {r.config.correct ? <>Correct form: <b>{String(r.config.correct)}</b>. </> : null}
                    {((r.config.terms ?? r.config.variants) as string[] | undefined)?.length ? <>Matches: {((r.config.terms ?? r.config.variants) as string[]).join(", ")}</> : null}
                  </p>
                ) : null}
                {user?.role === "admin" && (
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
