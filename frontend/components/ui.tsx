"use client";

import type { Outcome } from "@/lib/types";

export const OUTCOME_STYLE: Record<string, { label: string; chip: string; mark: string; dot: string }> = {
  supported: { label: "Supported", chip: "bg-emerald-50 text-emerald-800 ring-emerald-200", mark: "bg-emerald-100 decoration-emerald-500", dot: "bg-emerald-500" },
  contradicted: { label: "Contradicted", chip: "bg-red-50 text-red-800 ring-red-200", mark: "bg-red-100 decoration-red-500", dot: "bg-red-500" },
  unverified: { label: "Unverified", chip: "bg-amber-50 text-amber-800 ring-amber-200", mark: "bg-amber-100 decoration-amber-500", dot: "bg-amber-500" },
  needs_review: { label: "Needs review", chip: "bg-violet-50 text-violet-800 ring-violet-200", mark: "bg-violet-100 decoration-violet-500", dot: "bg-violet-500" },
  violation: { label: "Rule violation", chip: "bg-orange-50 text-orange-800 ring-orange-200", mark: "bg-orange-100 decoration-orange-500", dot: "bg-orange-500" },
  suggestion: { label: "Suggestion", chip: "bg-sky-50 text-sky-800 ring-sky-200", mark: "bg-sky-100 decoration-sky-500", dot: "bg-sky-500" },
};

export function OutcomeChip({ outcome }: { outcome: Outcome | string }) {
  const s = OUTCOME_STYLE[outcome] ?? OUTCOME_STYLE.suggestion;
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${s.chip}`}>{s.label}</span>;
}

const SEVERITY: Record<string, string> = {
  critical: "bg-red-600 text-white",
  major: "bg-orange-500 text-white",
  minor: "bg-slate-200 text-slate-700",
  info: "bg-slate-100 text-slate-500",
};

export function SeverityChip({ severity }: { severity: string }) {
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${SEVERITY[severity] ?? SEVERITY.info}`}>{severity}</span>;
}

const STATUS: Record<string, [string, string]> = {
  in_review: ["In review", "bg-sky-50 text-sky-800 ring-sky-200"],
  changes_requested: ["Changes requested", "bg-amber-50 text-amber-800 ring-amber-200"],
  signed_off: ["Signed off", "bg-emerald-50 text-emerald-800 ring-emerald-200"],
  needs_renewal: ["Sign-off needs renewal", "bg-red-50 text-red-800 ring-red-200"],
  rejected: ["Rejected", "bg-slate-100 text-slate-700 ring-slate-300"],
  valid: ["Valid", "bg-emerald-50 text-emerald-800 ring-emerald-200"],
  superseded: ["Superseded", "bg-slate-100 text-slate-600 ring-slate-300"],
  approved: ["Approved", "bg-emerald-50 text-emerald-800 ring-emerald-200"],
  retracted: ["Retracted", "bg-red-50 text-red-800 ring-red-200"],
  pending: ["Reviewing…", "bg-sky-50 text-sky-800 ring-sky-200"],
  done: ["Reviewed", "bg-emerald-50 text-emerald-800 ring-emerald-200"],
  failed: ["Review failed", "bg-red-50 text-red-800 ring-red-200"],
  active: ["Active", "bg-emerald-50 text-emerald-800 ring-emerald-200"],
  retired: ["Retired", "bg-slate-100 text-slate-600 ring-slate-300"],
};

export function StatusChip({ status }: { status: string }) {
  const [label, cls] = STATUS[status] ?? [status, "bg-slate-100 text-slate-700 ring-slate-300"];
  return <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}>{label}</span>;
}

const TIER: Record<string, string> = {
  public: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  internal: "bg-sky-50 text-sky-700 ring-sky-200",
  confidential: "bg-amber-50 text-amber-800 ring-amber-200",
  restricted: "bg-red-50 text-red-700 ring-red-200",
};

export function TierChip({ tier }: { tier: string }) {
  return <span className={`inline-flex rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ring-1 ring-inset ${TIER[tier] ?? TIER.internal}`}>{tier}</span>;
}

export function SourceChip({ source }: { source: string }) {
  const label = source === "rule" ? "Rule" : source === "local_model" ? "Local model" : "External model";
  const cls = source === "rule" ? "bg-slate-100 text-slate-600" : source === "local_model" ? "bg-indigo-50 text-indigo-700" : "bg-fuchsia-50 text-fuchsia-700";
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${cls}`} title="Where this finding came from">{label}</span>;
}

export function Button({
  children,
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" | "success" }) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700 disabled:bg-indigo-300",
    secondary: "bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:text-slate-400",
    danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300",
    success: "bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-300",
    ghost: "text-slate-600 hover:bg-slate-100 disabled:text-slate-300",
  }[variant];
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-lg border border-slate-200 bg-white shadow-sm ${className}`}>{children}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
      {label}
    </span>
  );
}

export function fmtDate(iso: string | null | undefined, withTime = false) {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return withTime
    ? d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
