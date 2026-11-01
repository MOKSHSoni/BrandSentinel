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
  const [url, setUrl] = useState("");
  const [source, setSource] = useState<"text" | "file" | "url">("text");
  const [sampleFiles, setSampleFiles] = useState<{ name: string; description: string; url: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function applySample(s: Sample) {
    setTitle(s.title);
    setChannel(s.channel);
    setGoal(s.goal);
    setText(s.content);
    setFile(null);
    setSource("text");
  }

  async function loadSampleFile(name: string) {
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/sample-files/${name}`);
      if (!res.ok) throw new Error(`Could not load ${name}.`);
      setFile(new File([await res.blob()], name));
      setSource("file");
      setTitle(name.endsWith(".png") ? "Festive banner (image)" : "Festive banner post (Word)");
      setChannel(name.endsWith(".png") ? "Display ad" : "Blog");
      setGoal("Get existing users to try cashback");
    } catch (e) {
      setError((e as Error).message);
    }
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
    api<{ name: string; description: string; url: string }[]>("/api/sample-files").then(setSampleFiles).catch(() => {});
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
    if (source === "file" && file) form.set("file", file);
    else if (source === "url") form.set("url", url);
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
          <div>
            <span className="text-sm font-medium text-slate-700">Content</span>
            <div className="mt-1 inline-flex rounded-md bg-slate-100 p-0.5 text-sm" role="tablist">
              {([["text", "Paste text"], ["file", "Upload a file"], ["url", "Check a web page"]] as const).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={source === k} onClick={() => setSource(k)}
                  className={`rounded px-3 py-1 ${source === k ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-600"}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          {source === "file" && (
            <div className="rounded-md border border-dashed border-slate-300 p-4">
              <label className="block text-sm">
                <input type="file" accept=".docx,.pdf,.txt,.md,.png,.jpg,.jpeg,.webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-indigo-700" />
                <span className="mt-1 block text-xs text-slate-500">Word (.docx), PDF, plain text or an image (.png, .jpg, .webp), up to 5 MB. Text inside images and Word pictures is read by OCR and checked too.</span>
              </label>
              {file && <p className="mt-2 text-sm text-slate-700">Using <b>{file.name}</b>.</p>}
            </div>
          )}
          {source === "url" && (
            <label className="block text-sm">
              <input value={url} onChange={(e) => setUrl(e.target.value)} type="url" placeholder="https://example.com/offer-page" className="w-full rounded-md border border-slate-300 px-3 py-2" />
              <span className="mt-1 block text-xs text-slate-500">Public pages only. The page text and up to 8 of its images are checked, including alt text.</span>
            </label>
          )}
          {source === "text" && (
            <label className="block text-sm">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={9} aria-label="Draft text" className="w-full rounded-md border border-slate-300 px-3 py-2 font-[inherit]" placeholder="Paste your draft here" />
            </label>
          )}
          <ErrorBox error={error} />
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={busy || !title.trim() || (source === "file" ? !file : source === "url" ? !url.trim() : !text.trim())}>
              {busy ? (source === "url" ? "Fetching page…" : "Uploading…") : "Check draft"}
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
        {sampleFiles.length > 0 && <h2 className="pt-2 text-sm font-semibold text-slate-700">Image samples</h2>}
        {sampleFiles.map((f) => (
          <Card key={f.name} className="p-4">
            <div className="text-sm font-medium text-slate-900">{f.name}</div>
            <p className="mt-1 text-xs text-slate-500">{f.description}</p>
            <div className="mt-3 flex gap-2">
              <Button variant="secondary" className="text-xs" onClick={() => loadSampleFile(f.name)}>Use file</Button>
              <a href={`${API_URL}${f.url}`} className="inline-flex items-center rounded-md px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50">Download</a>
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
