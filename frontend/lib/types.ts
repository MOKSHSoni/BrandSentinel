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
  decided_by: string | null;
  meta: { in_image?: number; image?: number; kind?: string; [k: string]: unknown };
  evidence_current: boolean;
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
  assets: ImageAsset[];
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

// ---------- Round 3 ----------

export interface OcrLine {
  text: string;
  box: [number, number, number, number];
  conf: number;
  contrast: { ratio: number; fg: string; bg: string; large: boolean } | null;
}

export interface ImageAsset {
  name: string;
  source: "upload" | "docx" | "web";
  alt: string | null;
  ocr_status: "ok" | "no_text" | "unavailable" | "failed";
  lines: OcrLine[];
  colours: { hex: string; share: number }[];
  width: number;
  height: number;
  preview: string;
  error?: string | null;
}

export interface ChainEvent {
  at: string;
  kind: "upload" | "review" | "decision" | "signoff" | "fact_change";
  text: string;
  audit_id?: number;
}

export interface EvidenceChain {
  finding: Finding & { decided_by: string | null };
  draft: { id: number; title: string; version: number; content_hash: string; rulebook_version: number; reviewed_at: string | null };
  evidence_status: { current: boolean; detail: string };
  events: ChainEvent[];
  history: { version: number; state: "this version" | "present" | "fixed" | "not present"; status: string | null; finding_id?: number }[];
  receipt: string;
}

export interface SimVerdict {
  outcome: string;
  fact: string | null;
  message: string;
}

export interface FactSimulation {
  read_only: true;
  fact: {
    key: string;
    from: { label: string; value_text: string; scope: string; effective_date: string };
    to: { label: string; value_text: string; scope: string; effective_date: string };
  };
  drafts: {
    draft_id: number;
    title: string;
    version: number;
    status: string;
    relation: string;
    signed_off: boolean;
    reason: string;
    claims: { quote: string; before: SimVerdict; after: SimVerdict; changed: boolean }[];
  }[];
  expected_draft_ids: number[];
  signoffs_to_renew: number;
  outcome_changes: Record<string, number>;
  drafts_with_changes: number;
  historic_versions: number;
  elapsed_ms: number;
}

export interface RuleSimulation {
  read_only: true;
  rule: { key: string; name: string; from_version: number; to_version: number };
  drafts: {
    draft_id: number;
    title: string;
    version: number;
    status: string;
    changes: { change: string; quote: string; message: string; blocking: boolean; severity: string; was?: string }[];
  }[];
  totals: { new: number; removed: number; now_blocking: number; no_longer_blocking: number };
  signoffs_to_renew: { signoff_id: number; draft_id: number; draft_title: string }[];
  elapsed_ms: number;
}

export type RadarLink = { type: "fact"; key: string } | { type: "rule"; key: string } | { type: "draft"; id: number };

export interface Radar {
  period: { days: number | null; since: string | null; until: string; versions_reviewed: number; drafts_reviewed: number };
  recurring: {
    key: string;
    label: string;
    rule_key: string | null;
    findings: number;
    versions_affected: number;
    versions_reviewed: number;
    examples: { draft_id: number; title: string; quote: string }[];
  }[];
  disagreement: {
    key: string;
    label: string;
    rule_key: string | null;
    decided: number;
    fixed: number;
    dismissed: number;
    overridden: number;
    disputed: number;
    rate: number | null;
    enough_data: boolean;
    recommendation?: string;
    reasons: { reason: string; status: string; draft_id: number; title: string; by: string | null }[];
  }[];
  open_risk: {
    blocking: { draft_id: number; title: string; version: number; status: string; open_blocking: number; critical: number }[];
    renewals: { signoff_id: number; draft_id: number; title: string; reason: string }[];
    stale_dependencies: { draft_id: number; title: string; fact: string; fact_key: string; problem: string }[];
  };
  freshness: {
    expired: { key: string; label: string; metric: string; valid_until: string; days: number }[];
    expiring: { key: string; label: string; metric: string; valid_until: string; days: number }[];
    no_end_date: { key: string; label: string; metric: string; valid_until: null }[];
    horizon_days: number;
    today: string;
  };
  actions: { severity: "high" | "medium"; text: string; link: RadarLink }[];
  notes: string[];
}
