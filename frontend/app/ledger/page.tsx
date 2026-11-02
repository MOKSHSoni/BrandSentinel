"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BlastEvent, Fact, FactSimulation } from "@/lib/types";
import { Button, Card, ErrorBox, PageHeader, Spinner, StatusChip, TierChip, fmtDate } from "@/components/ui";

interface Group {
  key: string;
  current: Fact;
  versions: Fact[];
}

const OUTCOME_TONE: Record<string, string> = {
  supported: "text-emerald-700",
  contradicted: "text-red-700",
  unverified: "text-amber-700",
  needs_review: "text-violet-700",
};

function Outcome({ o }: { o: string }) {
  return <span className={`font-medium ${OUTCOME_TONE[o] ?? "text-slate-700"}`}>{o.replace("_", " ")}</span>;
}

/** Brand Impact Simulator: propose a change, see what it would do, then confirm or cancel. */
function ChangeFact({ fact, onDone, onCancel }: { fact: Fact; onDone: (ev: BlastEvent, stale: boolean) => void; onCancel: () => void }) {
  const numeric = fact.value_num !== null;
  const [value, setValue] = useState(numeric ? String(fact.value_num) : fact.value_text);
  const [scope, setScope] = useState(fact.scope);
  const [effective, setEffective] = useState(new Date().toISOString().slice(0, 10));
  const [until, setUntil] = useState(fact.valid_until ?? "");
  const [sourceVersion, setSourceVersion] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"new" | "retract">("new");
  const [sim, setSim] = useState<FactSimulation | null>(null);
  const [busy, setBusy] = useState<"sim" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const changes = (): Record<string, unknown> => {
    const c: Record<string, unknown> = { effective_date: effective };
    if (numeric) c.value_num = Number(value);
    else c.value_text = value;
    if (scope && scope !== fact.scope) c.scope = scope;
    if (until && until !== fact.valid_until) c.valid_until = until;
    if (sourceVersion) c.source_version = sourceVersion;
    return c;
  };

  async function simulate() {
    setBusy("sim");
    setError(null);
    try {
      setSim(await api<FactSimulation>(`/api/facts/${fact.id}/simulate`, {
        method: "POST",
        json: { changes: mode === "new" ? changes() : {}, retract: mode === "retract" },
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function commit() {
    if (!sim) return;
    setBusy("commit");
    setError(null);
    try {
      type Result = { blast: BlastEvent; changed_since_preview?: boolean };
      const r = mode === "retract"
        ? await api<Result>(`/api/facts/${fact.id}/retract`, { method: "POST", json: { note, expected_draft_ids: sim.expected_draft_ids } })
        : await api<Result>(`/api/facts/${fact.id}/supersede`, { method: "POST", json: { changes: changes(), note, expected_draft_ids: sim.expected_draft_ids } });
      onDone(r.blast, Boolean(r.changed_since_preview));
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  // Any edit to the proposal discards the preview, so the admin always confirms exactly what they saw.
  function edit(setter: (v: string) => void, v: string) {
    setter(v);
    setSim(null);
  }
  const invalid = mode === "new" ? !value || (numeric && Number.isNaN(Number(value))) : !note.trim();

  return (
    <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/40 p-4">
      <div className="mb-3 flex gap-2 text-sm">
        <button onClick={() => { setMode("new"); setSim(null); }} className={`rounded-md px-3 py-1 ${mode === "new" ? "bg-indigo-600 text-white" : "bg-white ring-1 ring-slate-200"}`}>New version</button>
        <button onClick={() => { setMode("retract"); setSim(null); }} className={`rounded-md px-3 py-1 ${mode === "retract" ? "bg-red-600 text-white" : "bg-white ring-1 ring-slate-200"}`}>Retract</button>
      </div>
      {mode === "new" && (
        <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <label className="text-sm">
            <span className="text-slate-600">New value ({fact.unit || fact.kind})</span>
            <input value={value} onChange={(e) => edit(setValue, e.target.value)} type={numeric ? "number" : "text"} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Scope</span>
            <input value={scope} onChange={(e) => edit(setScope, e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Effective from</span>
            <input value={effective} onChange={(e) => edit(setEffective, e.target.value)} type="date" className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Valid until</span>
            <input value={until} onChange={(e) => edit(setUntil, e.target.value)} type="date" className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Source version</span>
            <input value={sourceVersion} onChange={(e) => edit(setSourceVersion, e.target.value)} placeholder={fact.source_version} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
        </div>
      )}
      <label className="mt-3 block text-sm">
        <span className="text-slate-600">{mode === "retract" ? "Reason (required)" : "Change note"}</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" placeholder={mode === "retract" ? "Why is this fact no longer true?" : "Q3 figures restated"} />
      </label>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button disabled={busy !== null || invalid} onClick={simulate}>{busy === "sim" ? "Simulating…" : sim ? "Preview again" : "Preview impact"}</Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <span className="text-xs text-slate-500">The preview changes nothing. Confirm afterwards to apply it.</span>
      </div>
      <ErrorBox error={error} />

      {sim && (
        <div className="mt-3 rounded-md bg-white p-3 text-sm ring-1 ring-indigo-200">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-indigo-800">Simulation · not applied</span>
            <span className="font-medium text-slate-900">
              {sim.fact.from.label} ({sim.fact.from.value_text}, {sim.fact.from.scope}) →{" "}
              {sim.fact.to ? `${sim.fact.to.label} (${sim.fact.to.value_text}, ${sim.fact.to.scope})` : "retracted"}
            </span>
          </div>
          <p className="text-slate-700">
            <b>{sim.drafts.length}</b> draft(s) would be flagged for re-review, <b>{sim.signoffs_to_renew}</b> sign-off(s) would need renewal,
            and re-review would change the outcome of claims in <b>{sim.drafts_with_changes}</b> draft(s)
            {Object.keys(sim.outcome_changes).length > 0 && <> ({Object.entries(sim.outcome_changes).map(([k, n]) => `${n} × ${k}`).join(", ")})</>}.
            {sim.historic_versions ? ` ${sim.historic_versions} older version(s) cited it too (history only).` : ""}{" "}
            <span className="text-xs text-slate-400">Computed in {sim.elapsed_ms} ms.</span>
          </p>
          {sim.drafts.length === 0 && <p className="mt-2 text-slate-500">No stored draft relies on {sim.fact.from.label}; the change only affects new reviews.</p>}
          <ul className="mt-2 space-y-2">
            {sim.drafts.map((d) => (
              <li key={d.draft_id} className="rounded-md border border-slate-200 p-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link href={`/drafts/${d.draft_id}`} className="font-medium text-indigo-700 hover:underline">{d.title}</Link>
                  <span className="text-xs text-slate-500">v{d.version} · {d.status.replace("_", " ")}{d.signed_off ? " · signed off → would need renewal" : ""}</span>
                </div>
                <p className="text-xs text-slate-500">{d.reason}</p>
                {d.claims.length > 0 && (
                  <table className="mt-1 w-full text-xs">
                    <thead className="text-left text-slate-400"><tr><th className="py-0.5 font-normal">Claim</th><th className="font-normal">Now</th><th className="font-normal">After the change</th></tr></thead>
                    <tbody>
                      {d.claims.map((c, i) => (
                        <tr key={i} className={c.changed ? "bg-amber-50" : ""}>
                          <td className="py-0.5 pr-2">“{c.quote}”</td>
                          <td className="pr-2"><Outcome o={c.before.outcome} />{c.before.fact ? ` (${c.before.fact})` : ""}</td>
                          <td><Outcome o={c.after.outcome} />{c.after.fact ? ` (${c.after.fact})` : ""}{c.changed ? " ← changes" : ""}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant={mode === "retract" ? "danger" : "success"} disabled={busy !== null} onClick={commit}>
              {busy === "commit" ? "Applying…" : mode === "retract" ? `Confirm: retract ${fact.label}` : `Confirm: approve ${sim.fact.to?.label}`}
            </Button>
            <Button variant="ghost" onClick={() => setSim(null)}>Discard preview</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function BlastResult({ ev, stale }: { ev: BlastEvent; stale: boolean }) {
  return (
    <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4">
      <h2 className="font-semibold text-red-900">Applied. Blast radius: {ev.affected.reason}</h2>
      {stale && <p className="mb-1 text-sm font-medium text-amber-800">The affected drafts changed between your preview and the confirmation; this list is the recalculated, actual result.</p>}
      <p className="text-sm text-red-800">
        {ev.affected.drafts.length} draft(s) flagged for re-review and {ev.affected.signoffs.length} sign-off(s) marked as needing renewal, in {ev.elapsed_ms} ms.
      </p>
      <ul className="mt-2 space-y-1 text-sm">
        {ev.affected.drafts.map((d) => (
          <li key={d.draft_id}>
            <Link href={`/drafts/${d.draft_id}`} className="font-medium text-red-900 underline">{d.title}</Link>{" "}
            <span className="text-red-700">v{d.version} · was {d.status_before.replace("_", " ")}{d.status_before === "signed_off" ? " → sign-off needs renewal" : ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AddFact({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ kind: "count", metric: "", aliases: "", value_num: "", value_text: "", unit: "", scope: "India", statement: "", effective_date: new Date().toISOString().slice(0, 10), valid_until: "", source: "", source_version: "", source_detail: "", sensitivity: "public" });
  const [error, setError] = useState<string | null>(null);
  const numeric = ["count", "percentage", "money", "rating", "duration"].includes(f.kind);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  async function submit() {
    setError(null);
    try {
      await api("/api/facts", {
        method: "POST",
        json: {
          ...f,
          aliases: f.aliases.split(",").map((s) => s.trim()).filter(Boolean),
          value_num: numeric && f.value_num ? Number(f.value_num) : null,
          value_text: f.value_text || null,
          valid_until: f.valid_until || null,
        },
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const input = (k: keyof typeof f, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <label className="text-sm">
      <span className="text-slate-600">{label}</span>
      <input value={f[k]} onChange={set(k)} {...props} className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5" />
    </label>
  );
  return (
    <Card className="mb-5 p-4">
      <h2 className="mb-3 font-semibold">Approve a new fact</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-sm">
          <span className="text-slate-600">Kind</span>
          <select value={f.kind} onChange={set("kind")} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5">
            {["count", "percentage", "money", "rating", "duration", "ranking", "comparison", "award", "testimonial"].map((k) => <option key={k}>{k}</option>)}
          </select>
        </label>
        {input("metric", "Metric (what it measures)", { placeholder: "App downloads" })}
        {input("aliases", "Words that mean this metric (comma-separated)", { placeholder: "downloads, installs" })}
        {numeric ? input("value_num", "Value", { type: "number" }) : input("value_text", "Approved wording")}
        {input("unit", "Unit")}
        {input("scope", "Scope")}
        {input("effective_date", "Effective from", { type: "date" })}
        {input("valid_until", "Valid until", { type: "date" })}
        {input("statement", "Approved statement")}
        {input("source", "Source")}
        {input("source_version", "Source version")}
        <label className="text-sm">
          <span className="text-slate-600">Sensitivity</span>
          <select value={f.sensitivity} onChange={set("sensitivity")} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5">
            {["public", "internal", "confidential", "restricted"].map((k) => <option key={k}>{k}</option>)}
          </select>
        </label>
      </div>
      <ErrorBox error={error} />
      <Button className="mt-3" onClick={submit}>Approve fact</Button>
    </Card>
  );
}

function LedgerInner() {
  const { user } = useAuth();
  const params = useSearchParams();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [open, setOpen] = useState<string | null>(params.get("fact"));
  const [changing, setChanging] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [blast, setBlast] = useState<{ ev: BlastEvent; stale: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = user?.role === "admin";

  const load = useCallback(() => api<Group[]>("/api/facts").then(setGroups).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    const k = params.get("fact");
    if (k && groups) document.getElementById(`fact-${k}`)?.scrollIntoView({ block: "center" });
  }, [params, groups]);

  return (
    <div>
      <PageHeader
        title="Brand Truth Ledger"
        subtitle="Approved facts held once, with metric, scope, dates, source and version. Every draft stores the fact versions it relied on, so a change shows exactly what needs re-review."
        actions={isAdmin ? <Button onClick={() => setAdding(!adding)}>{adding ? "Close" : "+ Approve new fact"}</Button> : undefined}
      />
      {user?.is_agency && <p className="mb-4 text-sm text-slate-500">Agency view: public facts only; internal documents behind each fact are hidden.</p>}
      {blast && <BlastResult ev={blast.ev} stale={blast.stale} />}
      {adding && <AddFact onDone={() => { setAdding(false); load(); }} />}
      <ErrorBox error={error} />
      {!groups ? <Spinner label="Loading ledger…" /> : (
        <div className="space-y-2">
          {groups.map((g) => {
            const c = g.current;
            const expanded = open === g.key;
            return (
              <Card key={g.key} className={`p-4 ${expanded ? "ring-2 ring-indigo-100" : ""}`}>
                <div id={`fact-${g.key}`} className="flex flex-wrap items-center gap-3">
                  <button onClick={() => setOpen(expanded ? null : g.key)} className="flex flex-1 items-center gap-3 text-left">
                    <span className="w-12 font-mono text-sm font-semibold text-indigo-700">{g.key}</span>
                    <span className="flex-1">
                      <span className="font-medium text-slate-900">{c.metric}</span>
                      <span className="ml-2 text-lg font-semibold text-slate-900">{c.value_text}</span>
                      <span className="ml-2 text-sm text-slate-500">{c.scope}</span>
                    </span>
                  </button>
                  <span className="text-xs text-slate-500">v{c.version} · {fmtDate(c.effective_date)}{c.valid_until ? ` → ${fmtDate(c.valid_until)}` : ""}</span>
                  {isAdmin ? (
                    <select
                      aria-label={`Sensitivity of ${g.key}`}
                      value={c.sensitivity}
                      onChange={async (e) => {
                        try {
                          await api(`/api/facts/${c.id}/sensitivity`, { method: "PATCH", json: { sensitivity: e.target.value } });
                          load();
                        } catch (err) {
                          setError((err as Error).message);
                        }
                      }}
                      className="rounded border border-slate-300 bg-white px-1 py-0.5 text-[11px] capitalize"
                      title="Reclassify (no new version, no blast radius)"
                    >
                      {["public", "internal", "confidential", "restricted"].map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  ) : (
                    <TierChip tier={c.sensitivity} />
                  )}
                  <StatusChip status={c.status} />
                  {isAdmin && c.status === "approved" && (
                    <Button variant="secondary" className="text-xs" onClick={() => { setOpen(g.key); setChanging(c.id); setBlast(null); }}>
                      Change or retract…
                    </Button>
                  )}
                </div>
                {changing === c.id && (
                  <ChangeFact fact={c} onCancel={() => setChanging(null)} onDone={(ev, stale) => { setChanging(null); setBlast({ ev, stale }); load(); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
                )}
                {expanded && (
                  <div className="mt-3 overflow-x-auto">
                    {c.statement && <p className="mb-2 text-sm text-slate-600">Approved statement: “{c.statement}”</p>}
                    {c.aliases?.length > 0 && <p className="mb-2 text-xs text-slate-500">Matched words: {c.aliases.join(", ")}{c.ambiguous_terms?.length ? ` · ambiguous (sent to review): ${c.ambiguous_terms.join(", ")}` : ""}</p>}
                    <table className="w-full text-xs">
                      <thead className="text-left text-slate-500">
                        <tr><th className="py-1 pr-3">Version</th><th className="pr-3">Value</th><th className="pr-3">Effective</th><th className="pr-3">Valid until</th><th className="pr-3">Source</th><th className="pr-3">Status</th><th>Note</th></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {[...g.versions].reverse().map((f) => (
                          <tr key={f.id}>
                            <td className="py-1.5 pr-3 font-medium">{f.label}</td>
                            <td className="pr-3">{f.value_text}</td>
                            <td className="pr-3">{fmtDate(f.effective_date)}</td>
                            <td className="pr-3">{fmtDate(f.valid_until)}</td>
                            <td className="pr-3">{f.source ? `${f.source} ${f.source_version}` : "(hidden)"}{f.source_detail && <div className="text-slate-400">{f.source_detail}</div>}</td>
                            <td className="pr-3"><StatusChip status={f.status} /></td>
                            <td className="text-slate-500">{f.change_note}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function LedgerPage() {
  return (
    <Suspense>
      <LedgerInner />
    </Suspense>
  );
}
