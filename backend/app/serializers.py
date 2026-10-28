"""JSON views. Evidence is filtered by role: agencies see fact IDs, not the internal documents behind them."""

from .models import Draft, DraftVersion, Fact, Finding, Rule, SignOff, User


def user_out(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role, "organisation": u.organisation,
            "is_agency": u.is_agency}


def can_see(viewer: User, fact: Fact) -> bool:
    return not viewer.is_agency or fact.sensitivity == "public"


def fact_out(f: Fact, viewer: User) -> dict:
    out = {
        "id": f.id, "key": f.key, "version": f.version, "label": f.label, "kind": f.kind, "metric": f.metric,
        "scope": f.scope, "status": f.status, "sensitivity": f.sensitivity,
        "effective_date": f.effective_date.isoformat(), "valid_until": f.valid_until.isoformat() if f.valid_until else None,
        "supersedes_id": f.supersedes_id, "superseded_by_id": f.superseded_by_id,
    }
    if can_see(viewer, f):
        out.update(value_text=f.value_text, value_num=f.value_num, unit=f.unit, statement=f.statement,
                   aliases=f.aliases, ambiguous_terms=f.ambiguous_terms, change_note=f.change_note)
    else:
        out.update(value_text="(internal)", value_num=None, unit="", statement="", aliases=[], ambiguous_terms=[],
                   change_note="")
    if not viewer.is_agency:
        out.update(source=f.source, source_version=f.source_version, source_detail=f.source_detail)
    return out


def rule_out(r: Rule, viewer: User) -> dict:
    out = {"id": r.id, "key": r.key, "version": r.version, "kind": r.kind, "name": r.name, "guideline": r.guideline,
           "severity": r.severity, "blocking": r.blocking, "status": r.status, "sensitivity": r.sensitivity,
           "updated_at": r.updated_at.isoformat() if r.updated_at else None}
    if not viewer.is_agency or r.sensitivity == "public":
        out["config"] = r.config
    return out


def finding_out(f: Finding, viewer: User, facts_by_id: dict[int, Fact]) -> dict:
    out = {
        "id": f.id, "check": f.check, "outcome": f.outcome, "severity": f.severity, "blocking": f.blocking,
        "start": f.start, "end": f.end, "quote": f.quote, "message": f.message, "explanation": f.explanation,
        "claim": f.claim, "source": f.source, "confidence": f.confidence, "status": f.status,
        "decision_reason": f.decision_reason, "decided_at": f.decided_at.isoformat() if f.decided_at else None,
        "suggestion": f.suggestion, "correction_check": f.correction_check,
        "fact": fact_out(f.fact, viewer) if f.fact else None,
        "rule": {"id": f.rule.id, "key": f.rule.key, "name": f.rule.name, "version": f.rule.version,
                 "guideline": f.rule.guideline} if f.rule else None,
        "candidates": [fact_out(facts_by_id[i], viewer) for i in f.candidate_fact_ids if i in facts_by_id],
    }
    if f.fact and not can_see(viewer, f.fact):
        out["message"] = f"Conflicts with approved fact {f.fact.label} (internal). Ask your Nimbus Pay contact for the figure." \
            if f.outcome == "contradicted" else f"Checked against approved fact {f.fact.label} (internal)."
        out["explanation"] = "The underlying figure and source are internal and not shown to agency accounts."
        out["suggestion"] = None
        if out["correction_check"]:
            out["correction_check"] = {k: v for k, v in out["correction_check"].items() if k not in ("before", "after", "withheld")}
    elif viewer.is_agency and f.fact and "Source:" in out["explanation"]:
        out["explanation"] = out["explanation"].split("Source:")[0].strip()
    return out


def version_meta(v: DraftVersion) -> dict:
    return {
        "id": v.id, "number": v.number, "content_hash": v.content_hash, "change_note": v.change_note,
        "source_filename": v.source_filename, "created_at": v.created_at.isoformat(),
        "created_by": v.created_by.name if v.created_by else None, "review_state": v.review_state,
        "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None, "rulebook_version": v.rulebook_version,
        "review_ms": v.review_ms, "effective_tier": v.effective_tier, "ai_status": v.ai_status,
    }


def version_out(v: DraftVersion, viewer: User, facts_by_id: dict[int, Fact]) -> dict:
    out = version_meta(v)
    out["content"] = v.content
    out["findings"] = [finding_out(f, viewer, facts_by_id) for f in sorted(v.findings, key=lambda f: (f.start, f.id))]
    out["citations"] = [{"fact": fact_out(c.fact, viewer), "relation": c.relation} for c in v.citations]
    return out


def counts(v: DraftVersion | None) -> dict:
    if v is None:
        return {}
    fs = v.findings
    return {
        "open_blocking": sum(1 for f in fs if f.status == "open" and f.blocking),
        "open": sum(1 for f in fs if f.status == "open"),
        "supported": sum(1 for f in fs if f.outcome == "supported"),
        "critical": sum(1 for f in fs if f.status == "open" and f.severity == "critical"),
    }


def signoff_out(s: SignOff) -> dict:
    return {
        "id": s.id, "draft_id": s.draft_id, "version_id": s.version_id,
        "version_number": s.version.number if s.version else None, "content_hash": s.content_hash,
        "rulebook_version": s.rulebook_version, "fact_labels": s.fact_labels, "overrides": s.overrides,
        "comment": s.comment, "signed_by": s.signed_by.name if s.signed_by else None,
        "signed_at": s.signed_at.isoformat(), "status": s.status, "renewal_reason": s.renewal_reason,
    }


def draft_summary(d: Draft) -> dict:
    latest = max(d.versions, key=lambda v: v.number) if d.versions else None
    return {
        "id": d.id, "title": d.title, "channel": d.channel, "goal": d.goal, "sensitivity": d.sensitivity,
        "status": d.status, "needs_rereview": d.needs_rereview, "rereview_reason": d.rereview_reason,
        "created_by": user_out(d.created_by), "created_at": d.created_at.isoformat(), "updated_at": d.updated_at.isoformat(),
        "latest_version": version_meta(latest) if latest else None, "counts": counts(latest),
    }
