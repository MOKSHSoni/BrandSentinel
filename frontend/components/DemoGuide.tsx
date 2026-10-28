"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";

const STEPS = [
  {
    who: "arjun@bluefin.example",
    as: "Arjun (agency)",
    title: "1. Check a draft",
    body: "New draft → “LinkedIn launch post” sample (or upload its DOCX). The count is Contradicted by F-12; the #1 ranking is Unverified.",
    go: "/drafts/new?sample=launch_post",
  },
  {
    who: "arjun@bluefin.example",
    as: "Arjun (agency)",
    title: "2. Correct it",
    body: "Accept the two checked fixes, then “Apply accepted fixes”. Each fix passed three checks: fact-backed, removes the issue, still serves the goal.",
    go: "/",
  },
  {
    who: "meera@nimbuspay.example",
    as: "Meera (manager)",
    title: "3. Sign off",
    body: "Open the post, compare v1 → v2, and sign off. The sign-off records the content hash, rulebook version and fact versions.",
    go: "/",
  },
  {
    who: "rahul@nimbuspay.example",
    as: "Rahul (brand admin)",
    title: "4. Change a fact",
    body: "Truth Ledger → F-12 → “New version” → 95,000. Blast radius lists every draft and sign-off that relied on F-12 v3.",
    go: "/ledger?fact=F-12",
  },
];

export default function DemoGuide() {
  const { user, login } = useAuth();
  const router = useRouter();
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    try {
      setHidden(localStorage.getItem("bs_hide_guide") === "1");
    } catch {}
  }, []);
  if (hidden) {
    return (
      <button className="mb-4 text-sm text-indigo-600 hover:underline" onClick={() => { setHidden(false); try { localStorage.removeItem("bs_hide_guide"); } catch {} }}>
        Show the 4-step demo guide
      </button>
    );
  }
  return (
    <div className="mb-6 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50 to-white p-5">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-slate-900">Try the end-to-end story (about 3 minutes)</h2>
          <p className="text-sm text-slate-600">Each step switches to the right person for you. You can also explore freely: every page works for every role it is shown to.</p>
        </div>
        <button className="text-sm text-slate-400 hover:text-slate-600" onClick={() => { setHidden(true); try { localStorage.setItem("bs_hide_guide", "1"); } catch {} }}>
          Hide
        </button>
      </div>
      <ol className="grid gap-3 md:grid-cols-4">
        {STEPS.map((s) => {
          const current = user?.email === s.who;
          return (
            <li key={s.title} className="flex flex-col rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-sm font-semibold text-slate-900">{s.title}</div>
              <div className="mb-2 text-xs text-indigo-700">as {s.as}</div>
              <p className="flex-1 text-xs leading-relaxed text-slate-600">{s.body}</p>
              <button
                className="mt-3 rounded-md bg-indigo-600 px-2 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                onClick={async () => {
                  if (!current) await login(s.who);
                  router.push(s.go);
                }}
              >
                {current ? "Go" : `Switch to ${s.as.split(" ")[0]} and go`}
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
