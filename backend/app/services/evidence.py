"""Evidence Chain: one finding traced from the sentence in the draft to its final resolution.

Everything comes from stored records (versions, findings, facts, rulebook, audit log, sign-offs, blast events);
nothing is inferred. Agency viewers get the same filtered evidence as the rest of the product.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, BlastEvent, DraftVersion, Fact, Finding, Rulebook, SignOff, User
from ..serializers import can_see, fact_out, finding_out
from .review import current_rulebook

OUTCOME_LABEL = {"supported": "Supported", "contradicted": "Contradicted", "unverified": "Unverified",
                 "needs_review": "Needs review", "violation": "Rule violation", "suggestion": "Suggestion"}
SOURCE_LABEL = {"rule": "a deterministic rule", "local_model": "the local AI model", "external_model": "the external AI model"}


def _match(a: Finding, b: Finding) -> bool:
    return a.check == b.check and a.rule_id == b.rule_id and a.quote == b.quote


def evidence_status(db: Session, f: Finding, viewer: User) -> dict:
    """Is the evidence behind this finding still current?"""
    if f.fact:
        fact = f.fact
        if fact.status == "approved":
            return {"current": True, "detail": f"{fact.label} is still the current approved version."}
        newer = db.scalar(select(Fact).where(Fact.key == fact.key, Fact.status == "approved"))
        if newer is None:
            return {"current": False, "detail": f"{fact.label} has been {fact.status}; there is no approved replacement."}
        value = newer.value_text if can_see(viewer, newer) else "an internal value"
        return {"current": False,
                "detail": f"Out of date: {fact.label} was superseded by {newer.label} ({value}), effective "
                          f"{newer.effective_date:%d %b %Y}. Re-run the review to check the draft against it."}
    reviewed = f.version.rulebook_version
    current = current_rulebook(db)
    if f.rule and reviewed and reviewed != current:
        notes = [b.note for b in db.scalars(select(Rulebook).where(Rulebook.version > reviewed).order_by(Rulebook.version))]
        return {"current": False, "detail": f"Reviewed under rulebook v{reviewed}; the current rulebook is v{current} "
                                            f"({'; '.join(notes)}). Re-run the review."}
    if f.check == "claim" and f.outcome == "unverified":
        return {"current": True, "detail": "No approved fact covers this claim, so no source is cited."}
    return {"current": True, "detail": "Evidence is current."}


def build_chain(db: Session, f: Finding, viewer: User) -> dict:
    v = f.version
    d = v.draft
    facts_by_id = {x.id: x for x in db.scalars(select(Fact))}
    status = evidence_status(db, f, viewer)
    events = [
        {"at": v.created_at.isoformat(), "kind": "upload",
         "text": f"v{v.number} created by {v.created_by.name if v.created_by else 'someone'}"
                 f"{f' from {v.source_filename}' if v.source_filename else ''} (hash {v.content_hash[:12]}…)."},
    ]
    if v.reviewed_at:
        events.append({"at": v.reviewed_at.isoformat(), "kind": "review",
                       "text": f"Found by {SOURCE_LABEL.get(f.source, f.source)} during review under rulebook "
                               f"v{v.rulebook_version}: {OUTCOME_LABEL.get(f.outcome, f.outcome)}."})
    for a in db.scalars(select(AuditLog).where(AuditLog.entity_type == "finding", AuditLog.entity_id == f.id)
                        .order_by(AuditLog.at)):
        events.append({"at": a.at.isoformat(), "kind": "decision", "text": f"{a.actor.name if a.actor else 'System'}: {a.summary}",
                       "audit_id": a.id})
    for s in db.scalars(select(SignOff).where(SignOff.version_id == v.id).order_by(SignOff.signed_at)):
        override = next((o for o in s.overrides if o.get("finding_id") == f.id), None)
        text = f"v{v.number} signed off by {s.signed_by.name} (sign-off now {s.status.replace('_', ' ')})."
        if override:
            text = f"Overridden at sign-off by {s.signed_by.name}: {override['reason']}. " + text
        events.append({"at": s.signed_at.isoformat(), "kind": "signoff", "text": text})
    if f.fact_id:
        for ev in db.scalars(select(BlastEvent).where(BlastEvent.old_fact_id == f.fact_id)):
            if ev.new_fact and can_see(viewer, ev.new_fact):
                change = f"{ev.old_fact.label} superseded by {ev.new_fact.label} ({ev.new_fact.value_text})"
            elif ev.new_fact:
                change = f"{ev.old_fact.label} superseded by {ev.new_fact.label}"
            else:
                change = f"{ev.old_fact.label} retracted"
            flagged = d.id in [x["draft_id"] for x in ev.affected.get("drafts", [])]
            events.append({"at": ev.created_at.isoformat(), "kind": "fact_change",
                           "text": change + ("; this draft was flagged for re-review." if flagged else ".")})

    history = []
    for other in sorted(d.versions, key=lambda x: x.number):
        if other.id == v.id:
            history.append({"version": other.number, "state": "this version", "status": f.status})
            continue
        twin = next((x for x in other.findings if _match(x, f)), None)
        if twin:
            history.append({"version": other.number, "state": "present", "status": twin.status,
                            "finding_id": twin.id})
        elif other.number > v.number:
            fixed = f.status in ("accepted", "edited") and other.number == v.number + 1 and other.change_note.startswith("Applied")
            history.append({"version": other.number, "state": "fixed" if fixed else "not present",
                            "status": None})
        else:
            history.append({"version": other.number, "state": "not present", "status": None})
    events.sort(key=lambda e: e["at"])

    out = finding_out(f, viewer, facts_by_id)
    out["decided_by"] = f.decided_by.name if f.decided_by else None
    return {
        "finding": out,
        "draft": {"id": d.id, "title": d.title, "version": v.number, "content_hash": v.content_hash,
                  "rulebook_version": v.rulebook_version, "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None},
        "evidence_status": status,
        "events": events,
        "history": history,
        "receipt": receipt(f, out, v, status),
    }


def receipt(f: Finding, out: dict, v: DraftVersion, status: dict) -> str:
    """A compact plain-text receipt for review e-mails, built from the role-filtered view."""
    lines = [
        "BrandSentinel evidence receipt",
        f"Draft: {v.draft.title} · v{v.number} (hash {v.content_hash[:12]}) · rulebook v{v.rulebook_version}",
        f"Finding: {OUTCOME_LABEL.get(f.outcome, f.outcome)}"
        + (f" ({f.severity})" if f.severity != "info" else "") + f" · {f.check.replace('_', ' ')} · found by {SOURCE_LABEL.get(f.source, f.source)}",
        f"Quote: “{f.quote}”",
        f"Why: {out['message']}",
    ]
    fact = out.get("fact")
    if fact:
        ev = f"Evidence: {fact['label']} · {fact['metric']} = {fact['value_text']} ({fact['scope']}), effective {fact['effective_date']}"
        if fact.get("valid_until"):
            ev += f", valid until {fact['valid_until']}"
        if fact.get("source"):
            ev += f" · source: {fact['source']} {fact['source_version']}"
        lines.append(ev)
    elif out.get("rule"):
        lines.append(f"Evidence: rule {out['rule']['key']} {out['rule']['name']} (v{out['rule']['version']}): {out['rule']['guideline']}")
    elif f.check == "claim" and f.outcome == "unverified":
        lines.append("Evidence: no approved fact covers this claim.")
    cc = out.get("correction_check") or {}
    if out.get("suggestion"):
        lines.append(f"Suggested fix: “{out['suggestion']}”")
    for key, label in (("supported", "a) fact-backed"), ("removes_violation", "b) removes issue"), ("serves_goal", "c) serves goal")):
        r = cc.get(key)
        if r:
            mark = "pass" if r["pass"] else ("fail" if r["pass"] is False else "to confirm")
            lines.append(f"  ({label}: {mark} — {r['detail']}")
    if f.status not in ("open", "info"):
        who = f.decided_by.name if f.decided_by else "someone"
        when = f" on {f.decided_at:%d %b %Y %H:%M} UTC" if f.decided_at else ""
        lines.append(f"Decision: {f.status} by {who}{when}" + (f" — {f.decision_reason}" if f.decision_reason else ""))
    else:
        lines.append("Decision: none yet" if f.status == "open" else "Decision: no action needed")
    lines.append(f"Evidence status: {status['detail']}")
    return "\n".join(lines)
