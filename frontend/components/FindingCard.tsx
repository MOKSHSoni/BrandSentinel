"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { CheckResult, Fact, Finding } from "@/lib/types";
import { Button, OutcomeChip, SeverityChip, SourceChip, StatusChip, fmtDate } from "./ui";

const CHECK_LABEL: Record<string, string> = {
  claim: "Claim",
  terminology: "Terminology",
  competitor: "Competitor term",
  banned_phrase: "Banned phrase",
  disclaimer: "Required disclaimer",
  tone: "Tone",
  confidential: "Confidentiality",
  injection: "Injected instructions",
};

function FactBox({ fact, title }: { fact: Fact; title?: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-2.5 text-xs">
      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold text-slate-800">{title ?? "Approved fact"} {fact.label}</span>
        <StatusChip status={fact.status} />
      </div>
      <dl className="grid grid-cols-[90px_1fr] gap-x-2 gap-y-0.5 text-slate-600">
        <dt>Metric</dt><dd className="text-slate-900">{fact.metric}</dd>
        <dt>Value</dt><dd className="font-medium text-slate-900">{fact.value_text}</dd>
        <dt>Scope</dt><dd>{fact.scope}</dd>
        <dt>Effective</dt><dd>{fmtDate(fact.effective_date)}{fact.valid_until ? ` → ${fmtDate(fact.valid_until)}` : ""}</dd>
        {fact.source && (<><dt>Source</dt><dd>{fact.source} {fact.source_version}</dd></>)}
        {fact.source_detail && (<><dt>Document</dt><dd className="italic">{fact.source_detail}</dd></>)}
      </dl>
    </div>
  );
}

function Check({ label, r }: { label: string; r: CheckResult | undefined }) {
  if (!r) return null;
  const icon = r.pass === true ? "✓" : r.pass === false ? "✗" : "?";
  const color = r.pass === true ? "text-emerald-600" : r.pass === false ? "text-red-600" : "text-amber-600";
  return (
    <li className="flex gap-2">
      <span className={`w-3 font-bold ${color}`}>{icon}</span>
      <span>
        <span className="font-medium text-slate-700">{label}:</span> <span className="text-slate-600">{r.detail}</span>
      </span>
    </li>
  );
}

export default function FindingCard({
  f,
  editable,
  selected,
  onSelect,
  onChanged,
}: {
  f: Finding;
  editable: boolean;
  selected: boolean;
  onSelect: () => void;
  onChanged: () => void;
}) {
  const [mode, setMode] = useState<"idle" | "edit" | "dismiss">("idle");
  const [text, setText] = useState(f.suggestion ?? f.quote);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cc = f.correction_check;
  const isClaimInfo = f.outcome === "supported";

  async function decide(action: string, extra: Record<string, string> = {}) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/findings/${f.id}/decision`, { method: "POST", json: { action, ...extra } });
      setMode("idle");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const resolved = ["accepted", "edited", "dismissed", "overridden"].includes(f.status);

  return (
    <div
      id={`finding-${f.id}`}
      onClick={onSelect}
      className={`cursor-pointer rounded-lg border bg-white p-3 text-sm transition ${selected ? "border-indigo-400 ring-2 ring-indigo-100" : "border-slate-200 hover:border-slate-300"} ${resolved ? "opacity-80" : ""}`}
    >
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <OutcomeChip outcome={f.outcome} />
        {!isClaimInfo && <SeverityChip severity={f.severity} />}
        <span className="text-xs text-slate-500">{CHECK_LABEL[f.check] ?? f.check}</span>
        {f.blocking && f.status === "open" && <span className="text-[11px] font-medium text-red-600">blocks sign-off</span>}
        <span className="ml-auto flex items-center gap-1.5">
          <SourceChip source={f.source} />
          {f.confidence != null && <span className="text-[11px] text-slate-400">conf. {f.confidence}</span>}
        </span>
      </div>
      <blockquote className="mb-2 border-l-2 border-slate-300 pl-2 text-slate-800">“{f.quote}”</blockquote>
      <p className="font-medium text-slate-900">{f.message}</p>
      {f.explanation && <p className="mt-1 text-xs text-slate-600">{f.explanation}</p>}

      {(f.fact || f.rule || f.candidates.length > 0) && (
        <div className="mt-2 space-y-2">
          {f.fact && <FactBox fact={f.fact} title={f.outcome === "supported" ? "Supported by" : "Approved fact"} />}
          {f.rule && (
            <div className="rounded-md border border-slate-200 bg-slate-50 p-2.5 text-xs">
              <div className="font-semibold text-slate-800">{f.rule.key} {f.rule.name} <span className="font-normal text-slate-500">(rule v{f.rule.version})</span></div>
              <p className="mt-0.5 text-slate-600">{f.rule.guideline}</p>
            </div>
          )}
          {f.candidates.length > 0 && !f.fact && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-600">Candidate facts for the reviewer:</p>
              {f.candidates.map((c) => <FactBox key={c.id} fact={c} title="Candidate" />)}
            </div>
          )}
        </div>
      )}

      {cc && (
        <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/50 p-2.5">
          {f.suggestion !== null && cc.after !== undefined ? (
            <>
              <p className="mb-1 text-xs font-semibold text-indigo-900">Suggested fix</p>
              <p className="text-xs text-slate-500 line-through decoration-red-400">{cc.before}</p>
              <p className="text-xs font-medium text-slate-900">{cc.after}</p>
            </>
          ) : (
            <p className="text-xs font-semibold text-slate-700">No safe fix suggested: a candidate failed the checks below. Edit the text yourself.</p>
          )}
          <ul className="mt-2 space-y-0.5 text-xs">
            <Check label="(a) Fact-backed" r={cc.supported} />
            <Check label="(b) Removes the issue" r={cc.removes_violation} />
            <Check label="(c) Serves the goal" r={cc.serves_goal} />
          </ul>
          {cc.edited && (
            <div className="mt-2 border-t border-indigo-100 pt-2">
              <p className="text-xs font-semibold text-slate-700">Your edit: “{cc.edited.text}”</p>
              <ul className="mt-1 space-y-0.5 text-xs">
                <Check label="(a) Fact-backed" r={cc.edited.supported} />
                <Check label="(b) Removes the issue" r={cc.edited.removes_violation} />
              </ul>
            </div>
          )}
        </div>
      )}

      {!isClaimInfo && (
        <div className="mt-3" onClick={(e) => e.stopPropagation()}>
          {resolved ? (
            <div className="flex items-center justify-between gap-2 text-xs">
              <span>
                <StatusChip status={f.status === "overridden" ? "superseded" : "done"} />{" "}
                <span className="font-medium capitalize text-slate-700">{f.status}</span>
                {f.decision_reason && <span className="text-slate-500">: {f.decision_reason}</span>}
              </span>
              {editable && f.status !== "overridden" && (
                <Button variant="ghost" className="text-xs" onClick={() => decide("reopen")} disabled={busy}>Undo</Button>
              )}
            </div>
          ) : editable && mode === "idle" ? (
            <div className="flex flex-wrap gap-2">
              {f.suggestion !== null && <Button variant="success" className="text-xs" disabled={busy} onClick={() => decide("accept")}>Accept fix</Button>}
              <Button variant="secondary" className="text-xs" onClick={() => { setText(f.suggestion ?? f.quote); setMode("edit"); }}>Edit</Button>
              <Button variant="ghost" className="text-xs" onClick={() => setMode("dismiss")}>Dismiss…</Button>
            </div>
          ) : null}
          {mode === "edit" && (
            <div className="space-y-2">
              <p className="text-xs text-slate-500">Replacement text for the highlighted part. It is re-checked against the ledger and rules.</p>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
              <div className="flex gap-2">
                <Button className="text-xs" disabled={busy} onClick={() => decide("edit", { text })}>Check &amp; use edit</Button>
                <Button variant="ghost" className="text-xs" onClick={() => setMode("idle")}>Cancel</Button>
              </div>
            </div>
          )}
          {mode === "dismiss" && (
            <div className="space-y-2">
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required, recorded in the audit log)" className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm" />
              <div className="flex gap-2">
                <Button variant="secondary" className="text-xs" disabled={busy || !reason.trim()} onClick={() => decide("dismiss", { reason })}>Dismiss</Button>
                <Button variant="ghost" className="text-xs" onClick={() => setMode("idle")}>Cancel</Button>
              </div>
            </div>
          )}
          {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
        </div>
      )}
    </div>
  );
}
