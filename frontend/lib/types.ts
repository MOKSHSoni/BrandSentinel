export type Role = "creator" | "manager" | "admin";

export interface User {
  id: number;
  email: string;
  name: string;
  role: Role;
  organisation: string;
  is_agency: boolean;
}

export interface Fact {
  id: number;
  key: string;
  version: number;
  label: string;
  kind: string;
  metric: string;
  scope: string;
  status: "approved" | "superseded" | "retracted";
  sensitivity: string;
  effective_date: string;
  valid_until: string | null;
  supersedes_id: number | null;
  superseded_by_id: number | null;
  value_text: string;
  value_num: number | null;
  unit: string;
  statement: string;
  aliases: string[];
  ambiguous_terms: string[];
  change_note: string;
  source?: string;
  source_version?: string;
  source_detail?: string;
}

export interface CheckResult {
  pass: boolean | null;
  detail: string;
}

export interface CorrectionCheck {
  supported: CheckResult;
  removes_violation: CheckResult;
  serves_goal: CheckResult;
  shown?: boolean;
  before?: string;
  after?: string;
  withheld?: string;
  edited?: { text: string; supported: CheckResult; removes_violation: CheckResult };
}

export type Outcome = "supported" | "contradicted" | "unverified" | "needs_review" | "violation" | "suggestion";

export interface Finding {
  id: number;
  check: string;
  outcome: Outcome;
  severity: "critical" | "major" | "minor" | "info";
  blocking: boolean;
  start: number;
  end: number;
  quote: string;
  message: string;
  explanation: string;
  claim: Record<string, unknown> | null;
  source: "rule" | "local_model" | "external_model";
  confidence: number | null;
  status: "open" | "info" | "accepted" | "edited" | "dismissed" | "overridden";
  decision_reason: string;
  suggestion: string | null;
  correction_check: CorrectionCheck | null;
  fact: Fact | null;
  rule: { id: number; key: string; name: string; version: number; guideline: string } | null;
  candidates: Fact[];
}

export interface VersionMeta {
  id: number;
  number: number;
  content_hash: string;
  change_note: string;
  source_filename: string;
  created_at: string;
  created_by: string | null;
  review_state: "pending" | "done" | "failed";
  reviewed_at: string | null;
  rulebook_version: number | null;
  review_ms: number | null;
  effective_tier: string;
  ai_status: string;
}

export interface Version extends VersionMeta {
  content: string;
  findings: Finding[];
  citations: { fact: Fact; relation: string }[];
}

export interface SignOff {
  id: number;
  draft_id: number;
  version_id: number;
  version_number: number | null;
  content_hash: string;
  rulebook_version: number;
  fact_labels: string[];
  overrides: { finding_id: number; quote: string; reason: string }[];
  comment: string;
  signed_by: string | null;
  signed_at: string;
  status: "valid" | "needs_renewal" | "superseded";
  renewal_reason: string;
  draft_title?: string;
}

export interface DraftSummary {
  id: number;
  title: string;
  channel: string;
  goal: string;
  sensitivity: string;
  status: "in_review" | "changes_requested" | "signed_off" | "needs_renewal" | "rejected";
  needs_rereview: boolean;
  rereview_reason: string;
  created_by: User;
  created_at: string;
  updated_at: string;
  latest_version: VersionMeta | null;
  counts: { open_blocking?: number; open?: number; supported?: number; critical?: number };
}

export interface AuditEntry {
  id: number;
  at: string;
  actor: string;
  action: string;
  summary: string;
  details: Record<string, unknown>;
  draft_id?: number | null;
}

export interface DraftDetail extends DraftSummary {
  versions: VersionMeta[];
  version: Version;
  is_latest: boolean;
  current_rulebook: number;
  signoffs: SignOff[];
  comments: { id: number; author: User; body: string; kind: string; version_number: number; created_at: string }[];
  audit: AuditEntry[];
}

export interface Rule {
  id: number;
  key: string;
  version: number;
  kind: string;
  name: string;
  guideline: string;
  severity: string;
  blocking: boolean;
  status: string;
  sensitivity: string;
  config?: Record<string, unknown>;
  updated_at: string | null;
}

export interface BlastEvent {
  id: number;
  created_at: string;
  change: string;
  actor: string | null;
  old_fact: { id: number; label: string; value_text: string };
  new_fact: { id: number; label: string; value_text: string } | null;
  affected: {
    drafts: { draft_id: number; title: string; version: number; status: string; relation: string; status_before: string }[];
    signoffs: { signoff_id: number; draft_id: number; version_id: number }[];
    historic_versions: number;
    reason: string;
  };
  elapsed_ms: number;
}
