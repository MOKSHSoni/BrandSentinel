"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { EvidenceChain as Chain } from "@/lib/types";
import { Button, Spinner, fmtDate } from "./ui";

const KIND_DOT: Record<string, string> = {
  upload: "bg-slate-400",
  review: "bg-indigo-500",
  decision: "bg-emerald-500",
  signoff: "bg-sky-500",
  fact_change: "bg-red-500",
};

const STATE_LABEL: Record<string, string> = {
  "this version": "this version",
  present: "still present",
  fixed: "fixed by the accepted correction",
  "not present": "not present",
};

/** The finding traced from the sentence in the draft to its resolution, loaded on demand. */
export default function EvidenceChain({ findingId }: { findingId: number }) {
  const [open, setOpen] = useState(false);
  const [chain, setChain] = useState<Chain | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function toggle() {
    const next = !open;
    setOpen(next);
    if (next) {
      setError(null);
      try {
        setChain(await api<Chain>(`/api/findings/${findingId}/chain`));
      } catch (e) {
        setError((e as Error).message);
      }
    }
  }

  async function copy() {
    if (!chain) return;
    try {
      await navigator.clipboard.writeText(chain.receipt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copy failed: select the receipt text below and copy it by hand.");
    }
  }

  return (
    <div className="mt-2" onClick={(e) => e.stopPropagation()}>
      <button onClick={toggle} className="text-xs font-medium text-indigo-700 hover:underline" aria-expanded={open}>
        {open ? "▾ Hide evidence chain" : "▸ Evidence chain"}
      </button>
      {open && (
        <div className="mt-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-xs">
          {error && <p className="text-red-700">{error}</p>}
          {!chain && !error && <Spinner label="Loading evidence…" />}
          {chain && (
            <div className="space-y-3">
              <p className={`rounded px-2 py-1 ${chain.evidence_status.current ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"}`}>
                {chain.evidence_status.current ? "Evidence current: " : "Evidence out of date: "}
                {chain.evidence_status.detail.replace(/^Out of date: /, "")}
              </p>
              <ol className="relative space-y-2 border-l border-slate-300 pl-4">
                {chain.events.map((e, i) => (
                  <li key={i}>
                    <span className={`absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full ${KIND_DOT[e.kind] ?? "bg-slate-400"}`} />
                    <span className="text-slate-400">{fmtDate(e.at, true)}</span>
                    <p className="text-slate-700">{e.text}</p>
                  </li>
                ))}
              </ol>
              {chain.history.length > 1 && (
                <div>
                  <p className="mb-1 font-medium text-slate-700">Across versions</p>
                  <ul className="flex flex-wrap gap-1.5">
                    {chain.history.map((h) => (
                      <li key={h.version} className={`rounded px-1.5 py-0.5 ${h.state === "this version" ? "bg-slate-800 text-white" : h.state === "fixed" ? "bg-emerald-100 text-emerald-800" : "bg-white ring-1 ring-slate-200"}`}>
                        v{h.version}: {STATE_LABEL[h.state]}
                        {h.status && h.state !== "this version" ? ` (${h.status})` : ""}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <p className="font-medium text-slate-700">Receipt</p>
                  <Button variant="secondary" className="px-2 py-0.5 text-xs" onClick={copy}>{copied ? "Copied" : "Copy receipt"}</Button>
                </div>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-[11px] leading-relaxed text-slate-700 ring-1 ring-slate-200">
                  {chain.receipt}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
