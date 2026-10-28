from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import current_user, issue_token, require
from ..config import settings
from ..db import get_db
from ..models import TIERS, AuditLog, EvalRun, Finding, ModelCall, Rule, User
from ..seed import SAMPLES, reset, verify_password
from ..serializers import user_out
from ..services import audit, llm
from ..services.intake import make_docx
from ..services.review import get_setting, set_setting

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {
        "ok": True,
        "local_model": {"enabled": settings.local_llm_enabled, "available": llm.local_available(),
                        "model": settings.local_llm_model},
        "external_model": {"configured": llm.external_available(), "model": settings.external_llm_model or None},
        "review_date": settings.today().isoformat(),
    }


@router.get("/auth/demo-users")
def demo_users(db: Session = Depends(get_db)):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.id))]


class Login(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: Login, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.email) == body.email.strip().lower()))
    if u is None or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong e-mail or password.")
    return {"token": issue_token(u), "user": user_out(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/samples")
def samples():
    return [{"key": k, **v} for k, v in SAMPLES.items()]


@router.get("/samples/{key}.docx")
def sample_docx(key: str):
    s = SAMPLES.get(key)
    if s is None:
        raise HTTPException(404, "Unknown sample.")
    return Response(make_docx(s["title"], s["content"]),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{key}.docx"'})


@router.get("/audit")
def audit_log(limit: int = 200, user: User = Depends(require("manager", "admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.at.desc()).limit(min(limit, 1000)))
    return [{"id": a.id, "at": a.at.isoformat(), "actor": a.actor.name if a.actor else "System", "action": a.action,
             "entity_type": a.entity_type, "entity_id": a.entity_id, "draft_id": a.draft_id, "summary": a.summary,
             "details": a.details} for a in rows]


@router.get("/insights")
def insights(user: User = Depends(require("manager", "admin")), db: Session = Depends(get_db)):
    """Recurring issues: which checks fire most and which ones reviewers disagree with."""
    rows = db.execute(select(Finding.check, Finding.rule_id, Finding.outcome, Finding.status, func.count())
                      .where(Finding.outcome != "supported")
                      .group_by(Finding.check, Finding.rule_id, Finding.outcome, Finding.status)).all()
    rules = {r.id: r for r in db.scalars(select(Rule))}
    by_key: dict[str, dict] = {}
    for check, rule_id, outcome, status, n in rows:
        label = f"{rules[rule_id].key} {rules[rule_id].name}" if rule_id in rules else \
            {"claim": f"Claim: {outcome.replace('_', ' ')}", "confidential": "Personal data", "injection": "Injected instructions"}.get(check, check)
        e = by_key.setdefault(label, {"label": label, "check": check, "total": 0, "open": 0, "accepted": 0,
                                       "edited": 0, "dismissed": 0, "overridden": 0})
        e["total"] += n
        if status in e:
            e[status] += n
    recurring = sorted(by_key.values(), key=lambda e: -e["total"])
    for e in recurring:
        decided = e["accepted"] + e["edited"] + e["dismissed"] + e["overridden"]
        e["disagreement_rate"] = round((e["dismissed"] + e["overridden"]) / decided, 2) if decided else None
    calls = list(db.scalars(select(ModelCall).order_by(ModelCall.at.desc()).limit(50)))
    last_eval = db.scalar(select(EvalRun).order_by(EvalRun.at.desc()).limit(1))
    return {
        "recurring": recurring,
        "model_calls": [{"id": c.id, "at": c.at.isoformat(), "purpose": c.purpose, "location": c.location,
                         "model": c.model, "tier": c.tier, "masked": c.masked, "ok": c.ok, "error": c.error,
                         "latency_ms": c.latency_ms, "version_id": c.version_id} for c in calls],
        "eval": {"at": last_eval.at.isoformat(), "mode": last_eval.mode, **last_eval.results} if last_eval else None,
    }


@router.get("/settings")
def get_settings(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"external_tiers": get_setting(db, "external_tiers", []), "tiers": TIERS,
            "brand_name": settings.brand_name, "default_scope": settings.brand_default_scope}


class SettingsBody(BaseModel):
    external_tiers: list[str]


@router.put("/settings")
def put_settings(body: SettingsBody, user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    allowed = [t for t in body.external_tiers if t in ("internal", "confidential")]
    set_setting(db, "external_tiers", allowed)
    audit.record(db, user, "settings.changed", "settings", None,
                 f"External model approved for tiers: {', '.join(allowed) or 'none (public only)'}.")
    db.commit()
    return {"external_tiers": allowed}


@router.post("/admin/reset")
def reset_demo(user: User = Depends(require("admin")), db: Session = Depends(get_db)):
    try:
        reset(db)
    except Exception:
        db.rollback()
        raise HTTPException(500, "Reset failed; the demo data was left unchanged.")
    return {"ok": True}
