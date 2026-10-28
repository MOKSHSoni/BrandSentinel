"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DraftDetail, Finding } from "@/lib/types";
import FindingCard from "@/components/FindingCard";
import HighlightedText from "@/components/HighlightedText";
import { Button, Card, ErrorBox, Spinner, StatusChip, TierChip, fmtDate } from "@/components/ui";

type Tab = "signoff" | "comments" | "audit";

function DiffView({ draftId, a, b }: { draftId: number; a: number; b: number }) {
  const [ops, setOps] = useState<{ op: string; text: string }[] | null>(null);
  useEffect(() => {
    api<{ ops: { op: string; text: string }[] }>(`/api/drafts/${draftId}/diff?a=${a}&b=${b}`).then((r) => setOps(r.ops)).catch(() => setOps([]));
  }, [draftId, a, b]);
  if (!ops) return <Spinner />;
  return (
    <div className="whitespace-pre-wrap text-[15px] leading-8 text-slate-800">
      {ops.map((o, i) =>
        o.op === "equal" ? <span key={i}>{o.text}</span> : o.op === "delete" ? (
          <del key={i} className="bg-red-100 text-red-800">{o.text}</del>
        ) : (
          <ins key={i} className="bg-emerald-100 text-emerald-900 no-underline">{o.text}</ins>
        ),
      )}
    </div>
  );
}

function SignOffPanel({ d, onDone }: { d: DraftDetail; onDone: () => void }) {
  const blocking = d.version.findings.filter((f) => f.status === "open" && f.blocking);
  const [overrides, setOverrides] = useState<Record<number, string>>({});
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reviewed = d.version.review_state === "done";
  const stale = d.version.rulebook_version !== d.current_rulebook;

  async function post(path: string, body: unknown) {
    setBusy(true);
    setError(null);
    try {
      await api(path, { method: "POST", json: body });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600">
        You are signing off <b>v{d.version.number}</b> (hash <code className="text-xs">{d.version.content_hash.slice(0, 12)}…</code>), checked against rulebook v{d.version.rulebook_version} and{" "}
        {d.version.citations.length ? d.version.citations.map((c) => c.fact.label).join(", ") : "no facts"}. If the text, a cited fact or the rulebook changes, this sign-off must be renewed.
      </p>
      {stale && <p className="text-sm text-amber-700">The rulebook changed since this review (now v{d.current_rulebook}). Re-run the review first.</p>}
      {blocking.length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
          <p className="mb-2 text-sm font-medium text-amber-900">{blocking.length} blocking finding(s) are open. Ask for changes, or override each one with a recorded reason:</p>
          {blocking.map((f) => (
            <label key={f.id} className="mb-2 block text-xs">
              <span className="text-slate-700">“{f.quote}”: {f.message}</span>
              <input
                value={overrides[f.id] ?? ""}
                onChange={(e) => setOverrides({ ...overrides, [f.id]: e.target.value })}
                placeholder="Override reason"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              />
            </label>
          ))}
        </div>
      )}
      <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="Comment (required to request changes or reject)" className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="success" disabled={busy || !reviewed || d.needs_rereview || stale} onClick={() => post(`/api/drafts/${d.id}/signoff`, { comment, overrides })}>
          Sign off v{d.version.number}
        </Button>
        <Button variant="secondary" disabled={busy || !comment.trim()} onClick={() => post(`/api/drafts/${d.id}/decision`, { decision: "changes_requested", comment })}>
          Request changes
        </Button>
        <Button variant="danger" disabled={busy || !comment.trim()} onClick={() => post(`/api/drafts/${d.id}/decision`, { decision: "rejected", comment })}>
          Reject
        </Button>
      </div>
    </div>
  );
}

export default function DraftPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [d, setD] = useState<DraftDetail | null>(null);
  const [viewVersion, setViewVersion] = useState<number | null>(null);
  const [diffFrom, setDiffFrom] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [comment, setComment] = useState("");
  const [tab, setTab] = useState<Tab>("signoff");

  const load = useCallback(async () => {
    try {
      const q = viewVersion ? `?version=${viewVersion}` : "";
      setD(await api<DraftDetail>(`/api/drafts/${id}${q}`));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [id, viewVersion]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (d?.version.review_state !== "pending") return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [d?.version.review_state, load]);

  const groups = useMemo(() => {
    const fs = d?.version.findings ?? [];
    return {
      open: fs.filter((f) => f.status === "open"),
      resolved: fs.filter((f) => ["accepted", "edited", "dismissed", "overridden"].includes(f.status)),
      supported: fs.filter((f) => f.outcome === "supported"),
    };
  }, [d]);

  if (error && !d) return <ErrorBox error={error} />;
  if (!d || !user) return <Spinner label="Loading draft…" />;

  const v = d.version;
  const isOwner = d.created_by.id === user.id;
  const canEdit = d.is_latest && (isOwner || user.role !== "creator") && d.status !== "rejected";
  const accepted = v.findings.filter((f) => f.status === "accepted" || f.status === "edited").length;
  const isManager = user.role === "manager" || user.role === "admin";

  async function action(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setViewVersion(null);
      setDiffFrom(null);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const select = (fid: number) => {
    setSelected(fid);
    document.getElementById(`finding-${fid}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div>
      <div className="mb-1 text-sm">
        <Link href="/" className="text-slate-500 hover:text-slate-700">← Drafts</Link>
      </div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{d.title}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <StatusChip status={d.status} />
            <span>{d.channel}</span>·<span>by {d.created_by.name} ({d.created_by.organisation})</span>
            {d.goal && <>· <span>Goal: <i>{d.goal}</i></span></>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {(d.needs_rereview || (d.is_latest && v.review_state === "done" && v.rulebook_version !== d.current_rulebook)) && (
            <Button variant="danger" disabled={busy} onClick={() => action(() => api(`/api/drafts/${d.id}/review`, { method: "POST" }))}>
              {busy ? "Re-checking…" : "Re-run review against current ledger"}
            </Button>
          )}
          {canEdit && accepted > 0 && (
            <Button variant="success" disabled={busy} onClick={() => action(() => api(`/api/drafts/${d.id}/apply-fixes`, { method: "POST" }))}>
              Apply {accepted} accepted fix{accepted > 1 ? "es" : ""} → v{d.versions.length + 1}
            </Button>
          )}
          {canEdit && !editing && (
            <Button variant="secondary" onClick={() => { setEditText(v.content); setEditing(true); }}>Edit text</Button>
          )}
        </div>
      </div>

      {d.needs_rereview && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <b>Blast radius:</b> {d.rereview_reason}. This draft relied on the old version, so it must be re-reviewed{d.signoffs.some((s) => s.status === "needs_renewal") ? " and its sign-off renewed" : ""}.
        </div>
      )}
      <ErrorBox error={error} />

      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-slate-500">Versions:</span>
        {d.versions.map((x) => (
          <button
            key={x.id}
            onClick={() => { setViewVersion(x.number === d.versions.length ? null : x.number); setDiffFrom(null); }}
            className={`rounded-md px-2.5 py-1 ${x.number === v.number ? "bg-slate-900 text-white" : "bg-white text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50"}`}
          >
            v{x.number}
          </button>
        ))}
        {v.number > 1 && (
          <button onClick={() => setDiffFrom(diffFrom ? null : v.number - 1)} className="ml-2 text-indigo-600 hover:underline">
            {diffFrom ? "Hide changes" : `Show changes from v${v.number - 1}`}
          </button>
        )}
        {!d.is_latest && <span className="text-amber-700">Viewing an older version (read-only)</span>}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-4">
          <Card className="p-5">
            {editing ? (
              <div className="space-y-2">
                <textarea value={editText} onChange={(e) => setEditText(e.target.value)} rows={12} className="w-full rounded-md border border-slate-300 p-3 text-[15px] leading-7" />
                <div className="flex gap-2">
                  <Button
                    disabled={busy}
                    onClick={() => {
                      const form = new FormData();
                      form.set("text", editText);
                      form.set("note", "Edited by hand");
                      action(() => api(`/api/drafts/${d.id}/versions`, { method: "POST", body: form })).then(() => setEditing(false));
                    }}
                  >
                    Save as v{d.versions.length + 1} and re-check
                  </Button>
                  <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                </div>
              </div>
            ) : diffFrom ? (
              <DiffView draftId={d.id} a={diffFrom} b={v.number} />
            ) : (
              <HighlightedText content={v.content} findings={v.findings} selected={selected} onSelect={select} />
            )}
          </Card>
          <Card className="p-4 text-xs text-slate-600">
            <div className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
              <div>Version <b>v{v.number}</b> · {v.change_note}{v.source_filename && ` (${v.source_filename})`} · {v.created_by} · {fmtDate(v.created_at, true)}</div>
              <div>Content hash <code>{v.content_hash.slice(0, 16)}…</code></div>
              <div className="flex items-center gap-1.5">Effective sensitivity <TierChip tier={v.effective_tier} /></div>
              <div>Rulebook v{v.rulebook_version ?? "—"} · review took {v.review_ms != null ? `${(v.review_ms / 1000).toFixed(1)} s` : "—"}</div>
              <div className="sm:col-span-2">{v.ai_status}</div>
            </div>
          </Card>

          <Card>
            <div className="flex border-b border-slate-200 text-sm">
              {(["signoff", "comments", "audit"] as Tab[]).map((t) => (
                <button key={t} onClick={() => setTab(t)} className={`px-4 py-2.5 ${tab === t ? "border-b-2 border-indigo-600 font-medium text-slate-900" : "text-slate-500"}`}>
                  {t === "signoff" ? "Sign-off" : t === "comments" ? `Comments (${d.comments.length})` : "Audit trail"}
                </button>
              ))}
            </div>
            <div className="p-4">
              {tab === "signoff" && (
                <div className="space-y-4">
                  {isManager && d.is_latest && d.status !== "rejected" && v.review_state === "done" &&
                    !d.signoffs.some((s) => s.status === "valid" && s.version_number === v.number) && (
                      <SignOffPanel d={d} onDone={() => action(async () => {})} />
                    )}
                  {d.signoffs.some((s) => s.status === "valid" && s.version_number === v.number) && (
                    <p className="text-sm text-emerald-700">v{v.number} is signed off. Any edit creates a new version that needs its own sign-off.</p>
                  )}
                  {!isManager && <p className="text-sm text-slate-500">A manager signs off each exact version. Resolve or explain every blocking finding first.</p>}
                  <div>
                    <h3 className="mb-2 text-sm font-semibold text-slate-700">Sign-off history</h3>
                    {d.signoffs.length === 0 && <p className="text-sm text-slate-500">Not signed off yet.</p>}
                    <ul className="space-y-2">
                      {d.signoffs.map((s) => (
                        <li key={s.id} className="rounded-md border border-slate-200 p-3 text-xs">
                          <div className="mb-1 flex items-center gap-2">
                            <StatusChip status={s.status} />
                            <b>v{s.version_number}</b> signed by {s.signed_by} · {fmtDate(s.signed_at, true)}
                          </div>
                          <div className="text-slate-600">
                            Hash <code>{s.content_hash.slice(0, 12)}…</code> · rulebook v{s.rulebook_version} · facts {s.fact_labels.join(", ") || "none"}
                          </div>
                          {s.renewal_reason && <div className="mt-1 text-red-700">{s.renewal_reason}</div>}
                          {s.overrides.length > 0 && <div className="mt-1 text-amber-800">Overrides: {s.overrides.map((o) => `“${o.quote}”: ${o.reason}`).join("; ")}</div>}
                          {s.comment && <div className="mt-1 italic text-slate-500">“{s.comment}”</div>}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}
              {tab === "comments" && (
                <div className="space-y-3">
                  {d.comments.map((c) => (
                    <div key={c.id} className="text-sm">
                      <span className="font-medium text-slate-900">{c.author.name}</span>{" "}
                      <span className="text-xs text-slate-500">on v{c.version_number} · {fmtDate(c.created_at, true)}</span>
                      {c.kind !== "comment" && <span className="ml-2"><StatusChip status={c.kind} /></span>}
                      <p className="text-slate-700">{c.body}</p>
                    </div>
                  ))}
                  <div className="flex gap-2">
                    <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Add a comment" className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm" />
                    <Button disabled={!comment.trim()} onClick={() => action(() => api(`/api/drafts/${d.id}/comments`, { method: "POST", json: { body: comment } })).then(() => setComment(""))}>Post</Button>
                  </div>
                </div>
              )}
              {tab === "audit" && (
                <ul className="space-y-2 text-xs">
                  {d.audit.map((a) => (
                    <li key={a.id} className="flex gap-3">
                      <span className="w-36 shrink-0 text-slate-400">{fmtDate(a.at, true)}</span>
                      <span className="w-24 shrink-0 font-medium text-slate-700">{a.actor}</span>
                      <span className="text-slate-600">{a.summary}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-3">
          {v.review_state === "pending" ? (
            <Card className="p-5">
              <Spinner label="Reviewing: rule checks, claim verification, then the AI judge…" />
              <p className="mt-2 text-xs text-slate-500">With the local model this takes up to a minute. The page updates by itself.</p>
            </Card>
          ) : v.review_state === "failed" ? (
            <ErrorBox error={v.ai_status} />
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-700">Open findings ({groups.open.length})</h2>
                <span className="text-xs text-slate-500">{groups.open.filter((f) => f.blocking).length} block sign-off</span>
              </div>
              {groups.open.length === 0 && <Card className="p-4 text-sm text-emerald-700">No open issues on this version.</Card>}
              {groups.open.map((f: Finding) => (
                <FindingCard key={f.id} f={f} editable={canEdit} selected={selected === f.id} onSelect={() => setSelected(f.id)} onChanged={load} />
              ))}
              {groups.resolved.length > 0 && <h2 className="pt-2 text-sm font-semibold text-slate-700">Decided ({groups.resolved.length})</h2>}
              {groups.resolved.map((f) => (
                <FindingCard key={f.id} f={f} editable={canEdit} selected={selected === f.id} onSelect={() => setSelected(f.id)} onChanged={load} />
              ))}
              {groups.supported.length > 0 && <h2 className="pt-2 text-sm font-semibold text-slate-700">Supported claims ({groups.supported.length})</h2>}
              {groups.supported.map((f) => (
                <FindingCard key={f.id} f={f} editable={false} selected={selected === f.id} onSelect={() => setSelected(f.id)} onChanged={load} />
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
