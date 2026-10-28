import difflib
import re
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..auth import current_user, require
from ..config import settings
from ..db import SessionLocal, get_db
from ..models import TIERS, AuditLog, Comment, Draft, DraftVersion, Fact, Finding, SignOff, User
from ..serializers import draft_summary, signoff_out, user_out, version_meta, version_out
from ..services import audit, governance, review
from ..services.analysis import FindingDraft, apply_fixes, check_correction
from ..services.intake import IntakeError, extract_text, normalise

router = APIRouter(prefix="/api", tags=["drafts"])


def review_in_background(version_id: int, actor_id: int | None) -> None:
    db = SessionLocal()
    try:
        v = db.get(DraftVersion, version_id)
        actor = db.get(User, actor_id) if actor_id else None
        try:
            review.run_review(db, v, actor)
            db.commit()
        except Exception as e:  # keep the draft usable and say what happened
            db.rollback()
            v = db.get(DraftVersion, version_id)
            v.review_state, v.ai_status = "failed", f"Review failed: {type(e).__name__}: {e}"
            db.commit()
            raise
    finally:
        db.close()


def visible_draft(db: Session, draft_id: int, user: User) -> Draft:
    d = db.get(Draft, draft_id)
    if d is None:
        raise HTTPException(404, "Draft not found.")
    if user.role == "creator" and d.created_by_id != user.id:
        raise HTTPException(403, "Creators can only open their own drafts.")
    return d


async def _read_content(text: str | None, file: UploadFile | None) -> tuple[str, str]:
    try:
        if file is not None and file.filename:
            return extract_text(file.filename, await file.read()), file.filename
        if text and text.strip():
            return normalise(text), ""
    except IntakeError as e:
        raise HTTPException(400, str(e))
    raise HTTPException(400, "Paste text or upload a .docx, .pdf or .txt file.")


@router.get("/drafts")
def list_drafts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Draft).options(selectinload(Draft.versions).selectinload(DraftVersion.findings)).order_by(Draft.updated_at.desc())
    if user.role == "creator":
        q = q.where(Draft.created_by_id == user.id)
    return [draft_summary(d) for d in db.scalars(q)]


@router.post("/drafts")
async def create_draft(
    background: BackgroundTasks,
    title: str = Form(...),
    goal: str = Form(""),
    channel: str = Form(""),
    sensitivity: str = Form("public"),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(require("creator", "manager", "admin")),
    db: Session = Depends(get_db),
):
    if sensitivity not in TIERS:
        raise HTTPException(400, f"Sensitivity must be one of {', '.join(TIERS)}.")
    content, filename = await _read_content(text, file)
    d = Draft(title=title.strip()[:200] or "Untitled", goal=goal.strip(), channel=channel.strip(),
              sensitivity=sensitivity, created_by_id=user.id)
    db.add(d)
    db.flush()
    v = review.new_version(db, d, content, user, "Initial upload", filename)
    audit.record(db, user, "draft.created", "draft", d.id, f"Created “{d.title}” v1" + (f" from {filename}" if filename else ""),
                 draft_id=d.id, content_hash=v.content_hash)
    db.commit()
    background.add_task(review_in_background, v.id, user.id)
    return {"id": d.id, "version": v.number}


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: int, version: int | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    facts_by_id = {f.id: f for f in db.scalars(select(Fact))}
    v = next((x for x in d.versions if x.number == version), None) if version else governance.latest_version(d)
    if v is None:
        raise HTTPException(404, "Version not found.")
    signoffs = list(db.scalars(select(SignOff).where(SignOff.draft_id == d.id).order_by(SignOff.signed_at.desc())))
    comments = list(db.scalars(select(Comment).where(Comment.draft_id == d.id).order_by(Comment.created_at)))
    log = list(db.scalars(select(AuditLog).where(AuditLog.draft_id == d.id).order_by(AuditLog.at.desc()).limit(100)))
    latest = governance.latest_version(d)
    return {
        **draft_summary(d),
        "versions": [version_meta(x) for x in d.versions],
        "version": version_out(v, user, facts_by_id),
        "is_latest": v.id == latest.id,
        "current_rulebook": review.current_rulebook(db),
        "signoffs": [signoff_out(s) for s in signoffs],
        "comments": [{"id": c.id, "author": user_out(c.author), "body": c.body, "kind": c.kind,
                      "version_number": c.version_number, "created_at": c.created_at.isoformat()} for c in comments],
        "audit": [{"id": a.id, "at": a.at.isoformat(), "actor": a.actor.name if a.actor else "System",
                   "action": a.action, "summary": a.summary, "details": a.details} for a in log],
    }


@router.post("/drafts/{draft_id}/versions")
async def add_version(
    draft_id: int,
    background: BackgroundTasks,
    note: str = Form("Edited"),
    text: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    d = visible_draft(db, draft_id, user)
    _check_editable(d, user)
    content, filename = await _read_content(text, file)
    latest = governance.latest_version(d)
    if review.content_hash(content) == latest.content_hash:
        raise HTTPException(400, "No changes: the text is identical to the latest version.")
    v = review.new_version(db, d, content, user, note.strip() or "Edited", filename)
    governance.on_new_version(db, d, v)
    audit.record(db, user, "version.created", "draft_version", v.id, f"Created v{v.number}: {v.change_note}",
                 draft_id=d.id, content_hash=v.content_hash)
    db.commit()
    background.add_task(review_in_background, v.id, user.id)
    return {"id": d.id, "version": v.number}


def _check_editable(d: Draft, user: User) -> None:
    if user.role == "creator" and d.created_by_id != user.id:
        raise HTTPException(403, "Only the draft's creator can change it.")
    if d.status == "rejected":
        raise HTTPException(400, "This draft was rejected. Start a new draft.")


@router.post("/drafts/{draft_id}/review")
def rerun_review(draft_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Re-check the latest version against the current ledger and rulebook (used after a blast-radius flag)."""
    d = visible_draft(db, draft_id, user)
    v = governance.latest_version(d)
    review.run_review(db, v, user)
    db.commit()
    return {"id": d.id, "version": v.number, "state": v.review_state}


class Decision(BaseModel):
    action: str  # accept | edit | dismiss | reopen
    text: str | None = None
    reason: str | None = None


@router.post("/findings/{finding_id}/decision")
def decide_finding(finding_id: int, body: Decision, user: User = Depends(current_user), db: Session = Depends(get_db)):
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found.")
    d = visible_draft(db, f.version.draft_id, user)
    if f.version.id != governance.latest_version(d).id:
        raise HTTPException(400, "Decisions apply to the latest version only.")
    if f.outcome == "supported":
        raise HTTPException(400, "Supported claims need no decision.")
    now = datetime.now(timezone.utc)
    result = {}
    if body.action == "accept":
        if f.suggestion is None:
            raise HTTPException(400, "There is no checked suggestion to accept. Edit the text instead.")
        f.status, f.decision_reason = "accepted", body.reason or ""
    elif body.action == "edit":
        if body.text is None:
            raise HTTPException(400, "Give the replacement text.")
        cc = dict(f.correction_check or {})
        fix_start, fix_end = _fix_span(f)
        facts, rules = review.ledger(db)
        stub = FindingDraft(check=f.check, outcome=f.outcome, severity=f.severity, blocking=f.blocking, start=f.start,
                            end=f.end, quote=f.quote, message=f.message, rule=f.rule)
        checked = check_correction(f.version.content, stub, body.text, fix_start, fix_end, facts, rules,
                                   settings.today(), settings.brand_default_scope)
        cc.update(edited={"text": body.text, "fix_start": fix_start, "fix_end": fix_end, **checked})
        f.correction_check = cc
        f.status, f.decision_reason = "edited", body.reason or ""
        result = checked
    elif body.action == "dismiss":
        if not (body.reason or "").strip():
            raise HTTPException(400, "Dismissing a finding needs a reason.")
        f.status, f.decision_reason = "dismissed", body.reason.strip()
    elif body.action == "reopen":
        f.status, f.decision_reason = "open", ""
    else:
        raise HTTPException(400, "Unknown action.")
    f.decided_by_id, f.decided_at = user.id, now
    audit.record(db, user, f"finding.{body.action}", "finding", f.id,
                 f"{body.action.title()} {f.check} finding “{f.quote[:60]}”" + (f": {f.decision_reason}" if f.decision_reason else ""),
                 draft_id=d.id, version=f.version.number)
    db.commit()
    return {"status": f.status, "check": result}


def _fix_span(f: Finding) -> tuple[int, int]:
    cc = f.correction_check or {}
    if "edited" in cc:
        return cc["edited"]["fix_start"], cc["edited"]["fix_end"]
    # Suggestions are stored with their own span; recover it from the before/after preview when present.
    return cc.get("fix_start", f.start), cc.get("fix_end", f.end)


@router.post("/drafts/{draft_id}/apply-fixes")
def apply_accepted(draft_id: int, background: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    _check_editable(d, user)
    v = governance.latest_version(d)
    fixes = []
    for f in v.findings:
        cc = f.correction_check or {}
        if f.status == "accepted" and f.suggestion is not None:
            fixes.append((cc.get("fix_start", f.start), cc.get("fix_end", f.end), f.suggestion))
        elif f.status == "edited" and "edited" in cc:
            e = cc["edited"]
            fixes.append((e["fix_start"], e["fix_end"], e["text"]))
    if not fixes:
        raise HTTPException(400, "Accept or edit at least one fix first.")
    content = apply_fixes(v.content, fixes)
    new = review.new_version(db, d, content, user, f"Applied {len(fixes)} accepted fix(es)")
    governance.on_new_version(db, d, new)
    audit.record(db, user, "version.created", "draft_version", new.id, f"Created v{new.number} by applying {len(fixes)} fix(es).",
                 draft_id=d.id, content_hash=new.content_hash)
    db.commit()
    background.add_task(review_in_background, new.id, user.id)
    return {"id": d.id, "version": new.number}


class SignOffBody(BaseModel):
    comment: str = ""
    overrides: dict[int, str] = {}


@router.post("/drafts/{draft_id}/signoff")
def sign_off(draft_id: int, body: SignOffBody, user: User = Depends(require("manager", "admin")), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    try:
        s = governance.sign_off(db, d, user, body.comment, body.overrides)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return signoff_out(s)


class DecisionBody(BaseModel):
    decision: str
    comment: str


@router.post("/drafts/{draft_id}/decision")
def manager_decision(draft_id: int, body: DecisionBody, user: User = Depends(require("manager", "admin")), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    try:
        governance.decide(db, d, user, body.decision, body.comment)
    except governance.GovernanceError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"status": d.status}


class CommentBody(BaseModel):
    body: str


@router.post("/drafts/{draft_id}/comments")
def add_comment(draft_id: int, body: CommentBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    if not body.body.strip():
        raise HTTPException(400, "Comment is empty.")
    v = governance.latest_version(d)
    db.add(Comment(draft_id=d.id, version_number=v.number, author_id=user.id, body=body.body.strip()))
    audit.record(db, user, "comment.added", "draft", d.id, f"Comment on v{v.number}: {body.body.strip()[:80]}", draft_id=d.id)
    db.commit()
    return {"ok": True}


@router.get("/drafts/{draft_id}/diff")
def diff(draft_id: int, a: int, b: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = visible_draft(db, draft_id, user)
    va = next((v for v in d.versions if v.number == a), None)
    vb = next((v for v in d.versions if v.number == b), None)
    if not va or not vb:
        raise HTTPException(404, "Version not found.")
    ta, tb = re.findall(r"\s+|[^\s]+", va.content), re.findall(r"\s+|[^\s]+", vb.content)
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=ta, b=tb, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "equal", "text": "".join(ta[i1:i2])})
        else:
            if i2 > i1:
                ops.append({"op": "delete", "text": "".join(ta[i1:i2])})
            if j2 > j1:
                ops.append({"op": "insert", "text": "".join(tb[j1:j2])})
    return {"a": a, "b": b, "ops": ops, "hash_a": va.content_hash, "hash_b": vb.content_hash}
