"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { API_URL, api } from "@/lib/api";
import { Button, Card, ErrorBox, PageHeader } from "@/components/ui";

interface Sample {
  key: string;
  title: string;
  channel: string;
  goal: string;
  content: string;
}

const TIERS = [
  ["public", "Public: may use any approved model"],
  ["internal", "Internal: local model unless the admin approves external use"],
  ["confidential", "Confidential: local model unless the admin approves; masked"],
  ["restricted", "Restricted: local model only"],
];

function NewDraftForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [samples, setSamples] = useState<Sample[]>([]);
  const [title, setTitle] = useState("");
  const [channel, setChannel] = useState("");
  const [goal, setGoal] = useState("");
  const [sensitivity, setSensitivity] = useState("public");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applySample(s: Sample) {
    setTitle(s.title);
    setChannel(s.channel);
    setGoal(s.goal);
    setText(s.content);
    setFile(null);
  }

  useEffect(() => {
    api<Sample[]>("/api/samples")
      .then((list) => {
        setSamples(list);
        const want = params.get("sample");
        const s = list.find((x) => x.key === want);
        if (s) applySample(s);
      })
      .catch(() => {});
  }, [params]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.set("title", title);
    form.set("channel", channel);
    form.set("goal", goal);
    form.set("sensitivity", sensitivity);
    if (file) form.set("file", file);
    else form.set("text", text);
    try {
      const res = await api<{ id: number }>("/api/drafts", { method: "POST", body: form });
      router.push(`/drafts/${res.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card className="p-5">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Title</span>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" placeholder="LinkedIn launch post" />
            </label>
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Channel</span>
              <input value={channel} onChange={(e) => setChannel(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" placeholder="LinkedIn, Email, Instagram…" />
            </label>
          </div>
          <label className="block text-sm">
            <span className="font-medium text-slate-700">Goal (intent line)</span>
            <input value={goal} onChange={(e) => setGoal(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" placeholder="Build trust in the new app" />
            <span className="mt-1 block text-xs text-slate-500">Every suggested correction is checked to make sure it still serves this goal.</span>
          </label>
          <label className="block text-sm">
            <span className="font-medium text-slate-700">Sensitivity</span>
            <select value={sensitivity} onChange={(e) => setSensitivity(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2">
              {TIERS.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-slate-500">Unreleased codenames or personal data raise it automatically.</span>
          </label>
          <div className="rounded-md border border-dashed border-slate-300 p-4">
            <label className="block text-sm">
              <span className="font-medium text-slate-700">Upload a file</span>
              <input type="file" accept=".docx,.pdf,.txt,.md" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="mt-1 block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-indigo-700" />
              <span className="mt-1 block text-xs text-slate-500">Word (.docx), PDF or plain text, up to 5 MB.</span>
            </label>
            {file && (
              <p className="mt-2 text-sm text-slate-700">
                Using <b>{file.name}</b>. <button type="button" className="text-indigo-600 underline" onClick={() => setFile(null)}>Use pasted text instead</button>
              </p>
            )}
          </div>
          {!file && (
            <label className="block text-sm">
              <span className="font-medium text-slate-700">…or paste the text</span>
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-[inherit]" placeholder="Paste your draft here" />
            </label>
          )}
          <ErrorBox error={error} />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || (!file && !text.trim()) || !title.trim()}>
              {busy ? "Uploading…" : "Check draft"}
            </Button>
            <span className="text-xs text-slate-500">Rules run first; the AI judge only handles what rules cannot decide.</span>
          </div>
        </form>
      </Card>
      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Sample drafts</h2>
        {samples.map((s) => (
          <Card key={s.key} className="p-4">
            <div className="text-sm font-medium text-slate-900">{s.title}</div>
            <p className="mt-1 line-clamp-3 text-xs text-slate-500">{s.content}</p>
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" className="text-xs" onClick={() => applySample(s)}>Use text</Button>
              <a href={`${API_URL}/api/samples/${s.key}.docx`} className="inline-flex items-center rounded-md px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50">
                Download .docx
              </a>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default function NewDraftPage() {
  return (
    <div>
      <PageHeader title="Check a new draft" subtitle="Each claim and term is checked against approved facts (with scope, source and version) and the brand's rules." />
      <Suspense>
        <NewDraftForm />
      </Suspense>
    </div>
  );
}
