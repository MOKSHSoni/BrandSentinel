"use client";

import type { Finding } from "@/lib/types";
import { OUTCOME_STYLE } from "./ui";

const RANK: Record<string, number> = { contradicted: 6, violation: 5, unverified: 4, needs_review: 3, suggestion: 2, supported: 1 };

/** Splits the draft at every finding boundary and colours each piece by the most serious finding covering it. */
export default function HighlightedText({
  content,
  findings,
  selected,
  onSelect,
}: {
  content: string;
  findings: Finding[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const shown = findings.filter((f) => !["dismissed", "overridden"].includes(f.status) && f.end > f.start);
  const cuts = new Set<number>([0, content.length]);
  shown.forEach((f) => {
    cuts.add(Math.max(0, f.start));
    cuts.add(Math.min(content.length, f.end));
  });
  const points = [...cuts].sort((a, b) => a - b);
  const pieces = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [s, e] = [points[i], points[i + 1]];
    const covering = shown.filter((f) => f.start <= s && f.end >= e);
    const top = covering.sort((a, b) => (RANK[b.outcome] ?? 0) - (RANK[a.outcome] ?? 0))[0];
    const text = content.slice(s, e);
    if (!top) {
      pieces.push(<span key={s}>{text}</span>);
      continue;
    }
    const style = OUTCOME_STYLE[top.outcome] ?? OUTCOME_STYLE.suggestion;
    const isSel = covering.some((f) => f.id === selected);
    const resolved = ["accepted", "edited"].includes(top.status);
    pieces.push(
      <mark
        key={s}
        onClick={() => onSelect(top.id)}
        title={covering.map((f) => `${OUTCOME_STYLE[f.outcome]?.label}: ${f.message}`).join("\n")}
        className={`cursor-pointer rounded-sm px-0.5 underline decoration-2 underline-offset-4 ${style.mark} ${isSel ? "ring-2 ring-indigo-400" : ""} ${resolved ? "opacity-60" : ""}`}
      >
        {text}
      </mark>,
    );
  }
  return <div className="whitespace-pre-wrap text-[15px] leading-8 text-slate-800">{pieces}</div>;
}
