"""Version-bound sign-off and blast radius."""

import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import BlastEvent, Citation, Comment, Draft, DraftVersion, Fact, Rule, Rulebook, SignOff, User
from . import audit
from .numbers import format_value
from .review import current_rulebook


class GovernanceError(ValueError):
    pass


def latest_version(draft: Draft) -> DraftVersion:
    return max(draft.versions, key=lambda v: v.number)


# ---------- sign-off ----------

def sign_off(db: Session, draft: Draft, manager: User, comment: str, overrides: dict[int, str]) -> SignOff:
    v = latest_version(draft)
    if v.review_state != "done":
        raise GovernanceError("The latest version has not finished review.")
    if draft.needs_rereview:
        raise GovernanceError(f"Re-run the review first: {draft.rereview_reason}")
    rb = current_rulebook(db)
    if v.rulebook_version != rb:
        raise GovernanceError(f"Reviewed under rulebook v{v.rulebook_version}; current is v{rb}. Re-run the review.")
    stale = [c.fact for c in v.citations if c.fact.status != "approved"]
    if stale:
        raise GovernanceError(f"{stale[0].label} is {stale[0].status}. Re-run the review.")

    open_blocking = [f for f in v.findings if f.status == "open" and f.blocking]
    missing = [f for f in open_blocking if not (overrides.get(f.id) or "").strip()]
    if missing:
        raise GovernanceError(
            f"{len(missing)} blocking finding(s) are still open. Resolve them or override each with a reason.")
    now = datetime.now(timezone.utc)
    override_log = []
    for f in open_blocking:
        f.status, f.decision_reason, f.decided_by_id, f.decided_at = "overridden", overrides[f.id].strip(), manager.id, now
        override_log.append({"finding_id": f.id, "quote": f.quote, "reason": f.decision_reason})

    for old in db.scalars(select(SignOff).where(SignOff.draft_id == draft.id, SignOff.status == "valid")):
        old.status, old.renewal_reason = "superseded", f"Replaced by sign-off of v{v.number}."
    cited = sorted(v.citations, key=lambda c: c.fact.key)
    s = SignOff(draft_id=draft.id, version_id=v.id, content_hash=v.content_hash, rulebook_version=rb,
                fact_ids=[c.fact_id for c in cited], fact_labels=[c.fact.label for c in cited],
                overrides=override_log, comment=comment, signed_by_id=manager.id)
    db.add(s)
    draft.status, draft.updated_at = "signed_off", now
    db.add(Comment(draft_id=draft.id, version_number=v.number, author_id=manager.id,
                   body=comment or "Signed off.", kind="signed_off"))
    db.flush()
    audit.record(db, manager, "signoff.created", "signoff", s.id,
                 f"Signed off v{v.number} (hash {v.content_hash[:12]}…, rulebook v{rb}, facts {', '.join(s.fact_labels) or 'none'}).",
                 draft_id=draft.id, content_hash=v.content_hash, rulebook_version=rb, facts=s.fact_labels,
                 overrides=override_log)
    return s


def decide(db: Session, draft: Draft, manager: User, decision: str, comment: str) -> None:
    if decision not in ("changes_requested", "rejected"):
        raise GovernanceError("Unknown decision.")
    if not comment.strip():
        raise GovernanceError("Give a reason.")
    v = latest_version(draft)
    draft.status = decision
    db.add(Comment(draft_id=draft.id, version_number=v.number, author_id=manager.id, body=comment, kind=decision))
    audit.record(db, manager, f"draft.{decision}", "draft", draft.id,
                 f"{'Requested changes on' if decision == 'changes_requested' else 'Rejected'} v{v.number}: {comment}",
                 draft_id=draft.id)


def on_new_version(db: Session, draft: Draft, v: DraftVersion) -> None:
    """Any edit after sign-off creates a version that needs its own sign-off."""
    for s in db.scalars(select(SignOff).where(SignOff.draft_id == draft.id, SignOff.status.in_(["valid", "needs_renewal"]))):
        s.status, s.renewal_reason = "superseded", f"Draft edited: v{v.number} needs its own sign-off."
    if draft.status in ("signed_off", "needs_renewal", "changes_requested"):
        draft.status = "in_review"
    draft.needs_rereview = False
    draft.rereview_reason = ""


# ---------- blast radius ----------

def affected_by(db: Session, fact_ids: list[int]) -> dict:
    latest = (select(DraftVersion.draft_id, func.max(DraftVersion.number).label("n"))
              .group_by(DraftVersion.draft_id).subquery())
    rows = db.execute(
        select(DraftVersion, Citation.fact_id, Citation.relation, latest.c.n)
        .join(Citation, Citation.version_id == DraftVersion.id)
        .join(latest, latest.c.draft_id == DraftVersion.draft_id)
        .where(Citation.fact_id.in_(fact_ids))
    ).all()
    current, historic, version_ids = {}, 0, set()
    for v, fact_id, relation, n in rows:
        version_ids.add(v.id)
        if v.number == n:
            current[v.id] = (v, fact_id, relation)
        else:
            historic += 1
    signoffs = list(db.scalars(select(SignOff).where(SignOff.version_id.in_(version_ids), SignOff.status == "valid"))) if version_ids else []
    return {"current": list(current.values()), "historic_versions": historic, "signoffs": signoffs}


def preview(db: Session, fact: Fact) -> dict:
    t0 = time.perf_counter()
    a = affected_by(db, [fact.id])
    return {
        "fact": fact.label,
        "drafts": [_draft_row(v, rel) for v, _, rel in a["current"]],
        "signoffs": [s.id for s in a["signoffs"]],
        "historic_versions": a["historic_versions"],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def _draft_row(v: DraftVersion, relation: str) -> dict:
    d = v.draft
    return {"draft_id": d.id, "title": d.title, "version": v.number, "status": d.status, "relation": relation}


def _apply_blast(db: Session, old: Fact, new: Fact | None, change: str, actor: User, reason: str) -> BlastEvent:
    t0 = time.perf_counter()
    a = affected_by(db, [old.id])
    flagged = []
    for v, _, rel in a["current"]:
        d = v.draft
        before = d.status
        d.needs_rereview, d.rereview_reason = True, reason
        if d.status == "signed_off":
            d.status = "needs_renewal"
        flagged.append({**_draft_row(v, rel), "status_before": before})
    renewed = []
    for s in a["signoffs"]:
        s.status, s.renewal_reason = "needs_renewal", reason
        renewed.append({"signoff_id": s.id, "draft_id": s.draft_id, "version_id": s.version_id})
        d = db.get(Draft, s.draft_id)
        if d.status == "signed_off":
            d.status = "needs_renewal"
    elapsed = (time.perf_counter() - t0) * 1000
    ev = BlastEvent(actor_id=actor.id, old_fact_id=old.id, new_fact_id=new.id if new else None, change=change,
                    affected={"drafts": flagged, "signoffs": renewed, "historic_versions": a["historic_versions"],
                              "reason": reason},
                    elapsed_ms=round(elapsed, 2))
    db.add(ev)
    db.flush()
    audit.record(db, actor, "blast_radius", "blast_event", ev.id,
                 f"{reason}: {len(flagged)} draft(s) flagged for re-review, {len(renewed)} sign-off(s) need renewal.",
                 drafts=[f["draft_id"] for f in flagged], signoffs=[r["signoff_id"] for r in renewed])
    return ev


FACT_FIELDS = ("kind", "metric", "aliases", "ambiguous_terms", "value_text", "value_num", "unit", "scope", "statement",
               "effective_date", "valid_until", "source", "source_version", "source_detail", "sensitivity")


def supersede_fact(db: Session, old: Fact, changes: dict, actor: User, note: str) -> tuple[Fact, BlastEvent]:
    if old.status != "approved":
        raise GovernanceError(f"{old.label} is {old.status}; only the current approved version can be changed.")
    data = {k: getattr(old, k) for k in FACT_FIELDS}
    data.update({k: v for k, v in changes.items() if k in FACT_FIELDS and v is not None})
    if "value_num" in changes and changes["value_num"] is not None and "value_text" not in changes:
        data["value_text"] = format_value(float(changes["value_num"]), data["kind"])
    if data["value_text"] != old.value_text and "statement" not in changes and old.value_text in (old.statement or ""):
        # Keep the approved wording in step with the new value.
        data["statement"] = old.statement.replace(old.value_text, data["value_text"])
    if "effective_date" not in changes:
        data["effective_date"] = settings.today()
    new = Fact(key=old.key, version=old.version + 1, status="approved", supersedes_id=old.id, change_note=note,
               created_by_id=actor.id, **data)
    db.add(new)
    db.flush()
    # The old version's window now ends where the successor starts (see verify.fact_window).
    old.status, old.superseded_by_id = "superseded", new.id
    reason = f"{old.key} changed: v{old.version} ({old.value_text}) → v{new.version} ({new.value_text})"
    audit.record(db, actor, "fact.superseded", "fact", new.id, f"{reason}. {note}".strip(),
                 old_fact_id=old.id, new_fact_id=new.id)
    ev = _apply_blast(db, old, new, "superseded", actor, reason)
    return new, ev


def retract_fact(db: Session, old: Fact, actor: User, note: str) -> BlastEvent:
    if old.status != "approved":
        raise GovernanceError(f"{old.label} is already {old.status}.")
    old.status, old.change_note = "retracted", note
    reason = f"{old.label} ({old.value_text}) retracted"
    audit.record(db, actor, "fact.retracted", "fact", old.id, f"{reason}: {note}")
    return _apply_blast(db, old, None, "retracted", actor, reason)


def create_fact(db: Session, data: dict, actor: User) -> Fact:
    key = data.get("key") or _next_key(db)
    if db.scalar(select(Fact).where(Fact.key == key)):
        raise GovernanceError(f"{key} already exists; add a new version instead.")
    f = Fact(key=key, version=1, status="approved", created_by_id=actor.id,
             **{k: data[k] for k in FACT_FIELDS if k in data and data[k] is not None})
    if f.value_num is not None and not f.value_text:
        f.value_text = format_value(f.value_num, f.kind)
    db.add(f)
    db.flush()
    audit.record(db, actor, "fact.created", "fact", f.id, f"Approved new fact {f.label}: {f.metric} = {f.value_text} ({f.scope}).")
    return f


def _next_key(db: Session) -> str:
    nums = [int(k.split("-")[1]) for k in db.scalars(select(Fact.key)) if k.startswith("F-") and k[2:].isdigit()]
    return f"F-{max(nums, default=0) + 1:02d}"


def change_rule(db: Session, rule: Rule, changes: dict, actor: User, note: str) -> Rulebook:
    for k in ("name", "guideline", "severity", "blocking", "config", "status", "sensitivity"):
        if k in changes and changes[k] is not None:
            setattr(rule, k, changes[k])
    rule.version += 1
    rule.updated_at = datetime.now(timezone.utc)
    return bump_rulebook(db, actor, f"{rule.key} v{rule.version}: {note or 'updated'}")


def bump_rulebook(db: Session, actor: User, note: str) -> Rulebook:
    old = current_rulebook(db)
    rb = Rulebook(version=old + 1, note=note)
    db.add(rb)
    db.flush()
    reason = f"Rulebook v{old} → v{rb.version} ({note})"
    renewed = []
    for s in db.scalars(select(SignOff).where(SignOff.status == "valid", SignOff.rulebook_version < rb.version)):
        s.status, s.renewal_reason = "needs_renewal", reason
        d = db.get(Draft, s.draft_id)
        if d.status == "signed_off":
            d.status = "needs_renewal"
        d.needs_rereview, d.rereview_reason = True, reason
        renewed.append(s.id)
    audit.record(db, actor, "rulebook.changed", "rulebook", rb.id, f"{reason}; {len(renewed)} sign-off(s) need renewal.",
                 signoffs=renewed)
    return rb
