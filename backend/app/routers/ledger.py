from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, require
from ..db import get_db
from ..models import TIERS, BlastEvent, Draft, Fact, Rule, Rulebook, SignOff, User
from ..serializers import draft_summary, fact_out, rule_out, signoff_out
from ..services import governance
from ..services.review import current_rulebook

router = APIRouter(prefix="/api", tags=["ledger"])


@router.get("/facts")
def list_facts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    facts = list(db.scalars(select(Fact).order_by(Fact.key, Fact.version)))
    groups: dict[str, list] = {}
    for f in facts:
        if user.is_agency and f.sensitivity != "public":
            continue
        groups.setdefault(f.key, []).append(fact_out(f, user))
    out = []
    for key, versions in groups.items():
        current = next((v for v in reversed(versions) if v["status"] == "approved"), versions[-1])
        out.append({"key": key, "current": current, "versions": versions})
    return sorted(out, key=lambda g: int(g["key"].split("-")[1]) if g["key"].split("-")[1].isdigit() else 0)


class FactBody(BaseModel):
    key: str | None = None
    kind: str | None = None
    metric: str | None = None
    aliases: list[str] | None = None
    ambiguous_terms: list[str] | None = None
    value_text: str | None = None
    value_num: float | None = None
    unit: str | None = None
    scope: str | None = None
    statement: str | None = None
    effective_date: date | None = None
    valid_until: date | None = None
    source: str | None = None
    source_version: str | None = None
    source_detail: str | None = None
    sensitivity: str | None = None


class ChangeBody(BaseModel):
    changes: FactBody
    note: str = ""


def _validate(body: FactBody) -> None:
    if body.sensitivity and body.sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")
    if body.kind and body.kind not in ("count", "percentage", "money", "rating", "duration", "ranking", "comparison",
                                       "award", "testimonial"):
        raise HTTPException(400, "Unknown fact kind.")


@router.post("/facts")
def create_fact(body: FactBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    _validate(body)
    for field in ("kind", "metric", "scope", "effective_date", "source", "source_version"):
        if getattr(body, field) in (None, ""):
            raise HTTPException(400, f"“{field}” is required.")
    if body.value_num is None and not body.value_text:
        raise HTTPException(400, "Give a value.")
    data = body.model_dump()
    data["aliases"] = data.get("aliases") or []
    data["ambiguous_terms"] = data.get("ambiguous_terms") or []
    data["sensitivity"] = data.get("sensitivity") or "public"
    try:
        f = governance.create_fact(db, data, user)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return fact_out(f, user)


def _fact(db: Session, fact_id: int) -> Fact:
    f = db.get(Fact, fact_id)
    if f is None:
        raise HTTPException(404, "Fact not found.")
    return f


@router.get("/facts/{fact_id}/blast-preview")
def blast_preview(fact_id: int, user: User = Depends(require("admin", "manager")), db: Session = Depends(get_db)):
    return governance.preview(db, _fact(db, fact_id))


@router.post("/facts/{fact_id}/supersede")
def supersede(fact_id: int, body: ChangeBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    _validate(body.changes)
    old = _fact(db, fact_id)
    try:
        new, ev = governance.supersede_fact(db, old, body.changes.model_dump(exclude_none=True), user, body.note)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"fact": fact_out(new, user), "blast": blast_out(ev)}


class NoteBody(BaseModel):
    note: str


@router.post("/facts/{fact_id}/retract")
def retract(fact_id: int, body: NoteBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    if not body.note.strip():
        raise HTTPException(400, "Give a reason for retracting.")
    try:
        ev = governance.retract_fact(db, _fact(db, fact_id), user, body.note)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"blast": blast_out(ev)}


def blast_out(ev: BlastEvent) -> dict:
    return {
        "id": ev.id, "created_at": ev.created_at.isoformat(), "change": ev.change,
        "actor": ev.actor.name if ev.actor else None,
        "old_fact": {"id": ev.old_fact.id, "label": ev.old_fact.label, "value_text": ev.old_fact.value_text},
        "new_fact": {"id": ev.new_fact.id, "label": ev.new_fact.label, "value_text": ev.new_fact.value_text} if ev.new_fact else None,
        "affected": ev.affected, "elapsed_ms": ev.elapsed_ms,
    }


@router.get("/blast-radius")
def blast_overview(user: User = Depends(require("admin", "manager")), db: Session = Depends(get_db)):
    events = list(db.scalars(select(BlastEvent).order_by(BlastEvent.created_at.desc()).limit(50)))
    flagged = list(db.scalars(select(Draft).where(Draft.needs_rereview.is_(True)).order_by(Draft.updated_at.desc())))
    renewals = list(db.scalars(select(SignOff).where(SignOff.status == "needs_renewal").order_by(SignOff.signed_at.desc())))
    return {"events": [blast_out(e) for e in events], "flagged_drafts": [draft_summary(d) for d in flagged],
            "signoffs_needing_renewal": [{**signoff_out(s), "draft_title": db.get(Draft, s.draft_id).title} for s in renewals]}


@router.get("/rules")
def list_rules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rules = list(db.scalars(select(Rule).order_by(Rule.key)))
    if user.is_agency:
        rules = [r for r in rules if r.sensitivity in ("public", "internal")]
    books = list(db.scalars(select(Rulebook).order_by(Rulebook.version.desc())))
    return {"current_version": current_rulebook(db), "rules": [rule_out(r, user) for r in rules],
            "history": [{"version": b.version, "note": b.note, "created_at": b.created_at.isoformat()} for b in books]}


class RuleBody(BaseModel):
    name: str | None = None
    guideline: str | None = None
    severity: str | None = None
    blocking: bool | None = None
    config: dict | None = None
    status: str | None = None
    sensitivity: str | None = None
    note: str = ""


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found.")
    if body.severity and body.severity not in ("critical", "major", "minor"):
        raise HTTPException(400, "Severity must be critical, major or minor.")
    if body.status and body.status not in ("active", "retired"):
        raise HTTPException(400, "Status must be active or retired.")
    rb = governance.change_rule(db, r, body.model_dump(exclude={"note"}), user, body.note)
    db.commit()
    return {"rule": rule_out(r, user), "rulebook_version": rb.version}
