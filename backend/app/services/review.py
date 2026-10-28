"""Run the pipeline for a stored draft version and persist findings, citations and the model call log."""

import hashlib
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppSetting, Citation, Draft, DraftVersion, Fact, Finding, ModelCall, Rule, Rulebook, User
from . import audit, llm
from .analysis import analyse
from .gateway import Masker, route_request
from .rules import PII_PATTERNS


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current_rulebook(db: Session) -> int:
    return db.scalar(select(func.max(Rulebook.version))) or 1


def get_setting(db: Session, key: str, default):
    row = db.get(AppSetting, key)
    return row.value.get("v", default) if row else default


def set_setting(db: Session, key: str, value) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = {"v": value}
    else:
        db.add(AppSetting(key=key, value={"v": value}))


def ledger(db: Session) -> tuple[list[Fact], list[Rule]]:
    facts = list(db.scalars(select(Fact).where(Fact.status != "draft")))
    rules = list(db.scalars(select(Rule).where(Rule.status == "active")))
    return facts, rules


def make_ai_factory(db: Session, version_id: int | None, rules: list[Rule], text: str, use_ai: bool):
    if not use_ai:
        return None
    confidential_terms = [t for r in rules if r.kind == "confidential_term" for t in r.config.get("terms", [])]
    pii_values = [m.group(0) for rx in PII_PATTERNS.values() for m in rx.finditer(text)]
    external_tiers = get_setting(db, "external_tiers", [])
    log_rows: list[ModelCall] = []

    def log(**kw):
        log_rows.append(ModelCall(version_id=version_id, **kw))

    def factory(tier: str) -> llm.AIContext:
        route = route_request(tier, llm.local_available(), llm.external_available(), external_tiers)
        if route.location == "blocked":
            log(purpose="review", location="blocked", model="-", tier=tier, masked=[], ok=True,
                error=route.reason, latency_ms=0)
        return llm.AIContext(route=route, tier=tier, masker=Masker(confidential_terms + pii_values),
                             confidential_terms=confidential_terms, log=log)

    return factory, log_rows


def run_review(db: Session, version: DraftVersion, actor: User | None = None, use_ai: bool = True) -> DraftVersion:
    t0 = time.time()
    draft = version.draft
    facts, rules = ledger(db)
    made = make_ai_factory(db, version.id, rules, version.content, use_ai)
    factory, log_rows = made if made else (None, [])
    result = analyse(version.content, facts, rules, goal=draft.goal, draft_tier=draft.sensitivity,
                     today=settings.today(), default_scope=settings.brand_default_scope, ai_factory=factory)

    for f in list(version.findings):
        db.delete(f)
    for c in list(version.citations):
        db.delete(c)
    db.flush()

    previous = _previous_decisions(db, version)
    for fd in result.findings:
        if fd.correction_check is not None:
            fd.correction_check.update(fix_start=fd.fix_start, fix_end=fd.fix_end)
        finding = Finding(
            version_id=version.id, check=fd.check, outcome=fd.outcome, severity=fd.severity, blocking=fd.blocking,
            start=fd.start, end=fd.end, quote=fd.quote, message=fd.message, explanation=fd.explanation,
            claim=fd.claim, fact_id=fd.fact.id if fd.fact else None, rule_id=fd.rule.id if fd.rule else None,
            candidate_fact_ids=[c.id for c in fd.candidates], suggestion=fd.suggestion,
            correction_check=fd.correction_check, source=fd.source, confidence=fd.confidence,
            status="info" if fd.outcome == "supported" else "open",
        )
        # A dismissal with a reason carries over to the same issue in the next version.
        prior = previous.get((fd.check, fd.quote, fd.outcome))
        if prior and prior.status == "dismissed":
            finding.status = "dismissed"
            finding.decision_reason = f"{prior.decision_reason} (carried over from v{version.number - 1})"
            finding.decided_by_id = prior.decided_by_id
            finding.decided_at = prior.decided_at
        db.add(finding)
    for fact_id, relation in result.citations.items():
        db.add(Citation(version_id=version.id, fact_id=fact_id, relation=relation))
    for row in log_rows:
        db.add(row)

    version.review_state = "done"
    version.reviewed_at = datetime.now(timezone.utc)
    version.rulebook_version = current_rulebook(db)
    version.review_ms = int((time.time() - t0) * 1000)
    version.effective_tier = result.effective_tier
    version.ai_status = result.ai_status
    draft.updated_at = datetime.now(timezone.utc)
    if draft.needs_rereview and version.number == max(v.number for v in draft.versions):
        draft.needs_rereview = False
        draft.rereview_reason = ""
    audit.record(db, actor, "review.completed", "draft_version", version.id,
                 f"Reviewed v{version.number}: {sum(1 for f in result.findings if f.outcome != 'supported')} issue(s), "
                 f"{sum(1 for f in result.findings if f.outcome == 'supported')} supported claim(s).",
                 draft_id=draft.id, rulebook_version=version.rulebook_version, tier=result.effective_tier,
                 ai_status=result.ai_status, review_ms=version.review_ms)
    db.flush()
    return version


def _previous_decisions(db: Session, version: DraftVersion) -> dict:
    if version.number <= 1:
        return {}
    prev = db.scalar(select(DraftVersion).where(DraftVersion.draft_id == version.draft_id,
                                                DraftVersion.number == version.number - 1))
    if not prev:
        return {}
    return {(f.check, f.quote, f.outcome): f for f in prev.findings}


def new_version(db: Session, draft: Draft, content: str, author: User, note: str, filename: str = "") -> DraftVersion:
    number = (max((v.number for v in draft.versions), default=0)) + 1
    v = DraftVersion(draft_id=draft.id, number=number, content=content, content_hash=content_hash(content),
                     change_note=note, source_filename=filename, created_by_id=author.id, review_state="pending")
    db.add(v)
    draft.versions.append(v)
    db.flush()
    return v
