"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { BlastEvent, Fact } from "@/lib/types";
import { Button, Card, ErrorBox, PageHeader, Spinner, StatusChip, TierChip, fmtDate } from "@/components/ui";

interface Group {
  key: string;
  current: Fact;
  versions: Fact[];
}

interface Preview {
  fact: string;
  drafts: { draft_id: number; title: string; version: number; status: string; relation: string }[];
  signoffs: number[];
  historic_versions: number;
  elapsed_ms: number;
}

function ChangeFact({ fact, onDone, onCancel }: { fact: Fact; onDone: (ev: BlastEvent) => void; onCancel: () => void }) {
  const numeric = fact.value_num !== null;
  const [value, setValue] = useState(numeric ? String(fact.value_num) : fact.value_text);
  const [effective, setEffective] = useState(new Date().toISOString().slice(0, 10));
  const [sourceVersion, setSourceVersion] = useState("");
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"new" | "retract">("new");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<Preview>(`/api/facts/${fact.id}/blast-preview`).then(setPreview).catch((e) => setError(e.message));
  }, [fact.id]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "retract") {
        const r = await api<{ blast: BlastEvent }>(`/api/facts/${fact.id}/retract`, { method: "POST", json: { note } });
        onDone(r.blast);
      } else {
        const changes: Record<string, unknown> = { effective_date: effective };
        if (numeric) changes.value_num = Number(value);
        else changes.value_text = value;
        if (sourceVersion) changes.source_version = sourceVersion;
        const r = await api<{ blast: BlastEvent }>(`/api/facts/${fact.id}/supersede`, { method: "POST", json: { changes, note } });
        onDone(r.blast);
      }
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50/40 p-4">
      <div className="mb-3 flex gap-2 text-sm">
        <button onClick={() => setMode("new")} className={`rounded-md px-3 py-1 ${mode === "new" ? "bg-indigo-600 text-white" : "bg-white ring-1 ring-slate-200"}`}>New version</button>
        <button onClick={() => setMode("retract")} className={`rounded-md px-3 py-1 ${mode === "retract" ? "bg-red-600 text-white" : "bg-white ring-1 ring-slate-200"}`}>Retract</button>
      </div>
      {mode === "new" ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="text-slate-600">New value ({fact.unit || fact.kind})</span>
            <input value={value} onChange={(e) => setValue(e.target.value)} type={numeric ? "number" : "text"} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Effective from</span>
            <input value={effective} onChange={(e) => setEffective(e.target.value)} type="date" className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
          <label className="text-sm">
            <span className="text-slate-600">Source version</span>
            <input value={sourceVersion} onChange={(e) => setSourceVersion(e.target.value)} placeholder={fact.source_version} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" />
          </label>
        </div>
      ) : null}
      <label className="mt-3 block text-sm">
        <span className="text-slate-600">{mode === "retract" ? "Reason (required)" : "Change note"}</span>
        <input value={note} onChange={(e) => setNote(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5" placeholder={mode === "retract" ? "Why is this fact no longer true?" : "Q3 figures restated"} />
      </label>
      <div className="mt-3 rounded-md bg-white p-3 text-sm ring-1 ring-slate-200">
        <p className="font-medium text-slate-800">Blast radius preview for {fact.label}</p>
        {!preview ? <Spinner /> : (
          <>
            <p className="text-slate-600">
              {preview.drafts.length} current draft(s) and {preview.signoffs.length} valid sign-off(s) rely on this version
              {preview.historic_versions ? `; ${preview.historic_versions} older version(s) cited it too` : ""}. Found in {preview.elapsed_ms} ms.
            </p>
            <ul className="mt-1 list-inside list-disc text-xs text-slate-600">
              {preview.drafts.map((x) => <li key={x.draft_id}>{x.title} (v{x.version}, {x.status.replace("_", " ")}, {x.relation})</li>)}
            </ul>
          </>
        )}
      </div>
      <ErrorBox error={error} />
      <div className="mt-3 flex gap-2">
        <Button variant={mode === "retract" ? "danger" : "primary"} disabled={busy || (mode === "retract" && !note.trim()) || !value} onClick={submit}>
          {mode === "retract" ? "Retract and flag affected content" : `Approve ${fact.key} v${fact.version + 1} and flag affected content`}
        </Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
}

function BlastResult({ ev }: { ev: BlastEvent }) {
  return (
    <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4">
      <h2 className="font-semibold text-red-900">Blast radius: {ev.affected.reason}</h2>
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
  const [blast, setBlast] = useState<BlastEvent | null>(null);
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
      {blast && <BlastResult ev={blast} />}
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
                  <TierChip tier={c.sensitivity} />
                  <StatusChip status={c.status} />
                  {isAdmin && c.status === "approved" && (
                    <Button variant="secondary" className="text-xs" onClick={() => { setOpen(g.key); setChanging(c.id); setBlast(null); }}>
                      New version / retract
                    </Button>
                  )}
                </div>
                {changing === c.id && (
                  <ChangeFact fact={c} onCancel={() => setChanging(null)} onDone={(ev) => { setChanging(null); setBlast(ev); load(); window.scrollTo({ top: 0, behavior: "smooth" }); }} />
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
