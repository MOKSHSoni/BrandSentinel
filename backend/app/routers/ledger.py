import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user, require
from ..config import settings
from ..db import get_db
from ..models import TIERS, BlastEvent, Draft, Fact, Rule, Rulebook, SignOff, User
from ..serializers import draft_summary, fact_out, rule_out, signoff_out
from ..services import audit, governance, simulate
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
    expected_draft_ids: list[int] | None = None  # from the simulation the admin looked at
    retract: bool = False  # simulate a retraction instead of a new version


def _validate(body: FactBody, base: Fact | None = None) -> None:
    """base is the version being changed; missing fields inherit from it, so check the merged result."""
    if body.sensitivity and body.sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")
    if body.kind and body.kind not in ("count", "percentage", "money", "rating", "duration", "ranking", "comparison",
                                       "award", "testimonial"):
        raise HTTPException(400, "Unknown fact kind.")
    for field in ("metric", "scope", "source", "source_version", "value_text"):
        value = getattr(body, field)
        if value is not None and not value.strip():
            raise HTTPException(400, f"“{field.replace('_', ' ')}” cannot be blank.")
    kind = body.kind or (base.kind if base else None)
    if body.value_num is not None:
        if body.value_num < 0:
            raise HTTPException(400, "The value cannot be negative.")
        if kind == "percentage" and body.value_num > 100:
            raise HTTPException(400, "A percentage cannot be above 100.")
        if kind == "rating" and body.value_num > 5:
            raise HTTPException(400, "A rating cannot be above 5.")
    effective = body.effective_date or (settings.today() if base else None)
    if base and effective < base.effective_date:
        raise HTTPException(400, f"The new version cannot start before {base.label} ({base.effective_date:%d %b %Y}).")
    until = body.valid_until or (base.valid_until if base else None)
    if effective and until and until < effective:
        which = "“Valid until”" if body.valid_until else f"The inherited end date ({until:%d %b %Y})"
        raise HTTPException(400, f"{which} is before the effective date. Give a later “valid until” date.")


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


@router.post("/facts/{fact_id}/simulate")
def simulate_fact_change(fact_id: int, body: ChangeBody, user: User = Depends(require("admin", "manager")),
                         db: Session = Depends(get_db)):
    """Brand Impact Simulator: re-verify every affected claim against the proposal. Changes nothing."""
    fact = _fact(db, fact_id)
    if not body.retract and fact.status == "approved":
        _validate(body.changes, fact)
    try:
        return simulate.simulate_fact(db, fact, body.changes.model_dump(exclude_none=True), user,
                                      retract=body.retract)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))


@router.post("/facts/{fact_id}/supersede")
def supersede(fact_id: int, body: ChangeBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    old = _fact(db, fact_id)
    if old.status == "approved":
        _validate(body.changes, old)
    try:
        new, ev = governance.supersede_fact(db, old, body.changes.model_dump(exclude_none=True), user, body.note)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    out = {"fact": fact_out(new, user), "blast": blast_out(ev)}
    if body.expected_draft_ids is not None:
        # The impact is recalculated at commit time; say so if it differs from what the admin previewed.
        actual = sorted(d["draft_id"] for d in ev.affected["drafts"])
        out["changed_since_preview"] = actual != sorted(body.expected_draft_ids)
    return out


class SensitivityBody(BaseModel):
    sensitivity: str
    note: str = ""


@router.patch("/facts/{fact_id}/sensitivity")
def set_fact_sensitivity(fact_id: int, body: SensitivityBody, user: User = Depends(require("admin")),
                         db: Session = Depends(get_db)):
    """Reclassify a fact (all its versions). The value is unchanged, so no new version and no blast radius."""
    if body.sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")
    f = _fact(db, fact_id)
    before = f.sensitivity
    for v in db.scalars(select(Fact).where(Fact.key == f.key)):
        v.sensitivity = body.sensitivity
    audit.record(db, user, "fact.sensitivity", "fact", f.id,
                 f"{f.key} reclassified from {before} to {body.sensitivity}" + (f": {body.note}" if body.note else "."))
    db.commit()
    return fact_out(f, user)


class NoteBody(BaseModel):
    note: str
    expected_draft_ids: list[int] | None = None


@router.post("/facts/{fact_id}/retract")
def retract(fact_id: int, body: NoteBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    if not body.note.strip():
        raise HTTPException(400, "Give a reason for retracting.")
    try:
        ev = governance.retract_fact(db, _fact(db, fact_id), user, body.note)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    out = {"blast": blast_out(ev)}
    if body.expected_draft_ids is not None:
        out["changed_since_preview"] = sorted(d["draft_id"] for d in ev.affected["drafts"]) != sorted(body.expected_draft_ids)
    return out


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


def _config_problem(kind: str, cfg: dict) -> str | None:
    """A bad rule would break every later review, so nothing invalid is saved or simulated."""
    def strings(key):
        v = cfg.get(key, [])
        return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)

    def number(key, low, high):
        v = cfg.get(key)
        return isinstance(v, (int, float)) and not isinstance(v, bool) and low <= v <= high

    if kind == "terminology":
        if not isinstance(cfg.get("correct"), str) or not cfg["correct"].strip():
            return "A terminology rule needs the correct form."
        if not strings("variants"):
            return "Variants must be a list of words."
    elif kind in ("competitor", "banned_phrase", "tone", "confidential_term"):
        if not strings("terms"):
            return "Terms must be a list of words."
    elif kind == "disclaimer":
        if not isinstance(cfg.get("required"), str) or not cfg["required"].strip():
            return "A disclaimer rule needs the required wording."
        for key in ("trigger_regex", "present_regex"):
            try:
                re.compile(cfg.get(key, ""))
            except (re.error, TypeError):
                return f"“{key.replace('_', ' ')}” is not a valid pattern."
            if not cfg.get(key):
                return f"“{key.replace('_', ' ')}” cannot be blank."
    elif kind == "accessibility":
        if not number("min_contrast", 1, 21) or not number("min_contrast_large", 1, 21):
            return "Contrast limits must be numbers between 1 and 21."
    elif kind == "palette":
        colours = cfg.get("colors")
        if not isinstance(colours, list) or not colours or not all(
                isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c.strip()) for c in colours):
            return "Palette colours must be hex values such as #4F46E5."
        if not number("tolerance", 0, 442) or not number("min_share", 0, 1):
            return "Palette tolerance or minimum share is out of range."
    return None


@router.post("/rules/{rule_id}/simulate")
def simulate_rule_change(rule_id: int, body: "RuleBody", user: User = Depends(require("admin", "manager")),
                         db: Session = Depends(get_db)):
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found.")
    _validate_rule(body, r)
    return simulate.simulate_rule(db, r, body.model_dump(exclude={"note"}, exclude_none=True))


@router.patch("/rules/{rule_id}/sensitivity")
def set_rule_sensitivity(rule_id: int, body: SensitivityBody, user: User = Depends(require("admin")),
                         db: Session = Depends(get_db)):
    """Reclassify a rule. Its checks are unchanged, so the rulebook version and sign-offs are not affected."""
    if body.sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found.")
    before, r.sensitivity = r.sensitivity, body.sensitivity
    audit.record(db, user, "rule.sensitivity", "rule", r.id,
                 f"{r.key} reclassified from {before} to {body.sensitivity}" + (f": {body.note}" if body.note else "."))
    db.commit()
    return rule_out(r, user)


def _validate_rule(body: "RuleBody", rule: Rule) -> None:
    if body.guideline is not None and not body.guideline.strip():
        raise HTTPException(400, "The guideline cannot be blank.")
    if body.config is not None:
        problem = _config_problem(rule.kind, body.config)
        if problem:
            raise HTTPException(400, problem)
    if body.severity and body.severity not in ("critical", "major", "minor"):
        raise HTTPException(400, "Severity must be critical, major or minor.")
    if body.status and body.status not in ("active", "retired"):
        raise HTTPException(400, "Status must be active or retired.")
    if body.sensitivity and body.sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")


@router.put("/rules/{rule_id}")
def update_rule(rule_id: int, body: RuleBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    r = db.get(Rule, rule_id)
    if r is None:
        raise HTTPException(404, "Rule not found.")
    _validate_rule(body, r)
    rb = governance.change_rule(db, r, body.model_dump(exclude={"note"}), user, body.note)
    db.commit()
    return {"rule": rule_out(r, user), "rulebook_version": rb.version}
