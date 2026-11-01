"""Governance Drift Radar: where governance is failing or creating review work, from stored records only.

Two kinds of numbers are kept apart: what happened in the chosen period (findings in versions reviewed in the
window, decisions made in the window) and what is unresolved right now. Every rate shows its numerator and
denominator; small samples are labelled instead of being presented as a trend.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Citation, Draft, DraftVersion, Fact, Finding, Rule, SignOff, User

MIN_DECISIONS = 3  # below this a disagreement rate is shown as "too few decisions to judge"
EXPIRY_HORIZON_DAYS = 30


def _label(f: Finding, rules: dict) -> tuple[str, str]:
    if f.rule_id in rules:
        r = rules[f.rule_id]
        return f"rule:{r.key}", f"{r.key} {r.name}"
    if f.check == "claim":
        return f"claim:{f.outcome}", f"Claims: {f.outcome.replace('_', ' ')}"
    names = {"confidential": "Personal data", "injection": "Injected instructions", "image": "Unreadable image text"}
    return f"check:{f.check}", names.get(f.check, f.check.replace("_", " ").title())


def build_radar(db: Session, viewer: User, days: int | None) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days) if days else None
    rules = {r.id: r for r in db.scalars(select(Rule))}

    reviewed_q = select(DraftVersion).where(DraftVersion.review_state == "done")
    if since:
        reviewed_q = reviewed_q.where(DraftVersion.reviewed_at >= since)
    reviewed = list(db.scalars(reviewed_q))
    reviewed_ids = {v.id for v in reviewed}

    # 1. Recurring findings in the period: how many reviewed versions each check fired in.
    recurring: dict[str, dict] = {}
    if reviewed_ids:
        for f in db.scalars(select(Finding).where(Finding.version_id.in_(reviewed_ids), Finding.outcome != "supported")):
            key, label = _label(f, rules)
            e = recurring.setdefault(key, {"key": key, "label": label, "rule_key": rules[f.rule_id].key if f.rule_id in rules else None,
                                           "findings": 0, "versions": set(), "examples": []})
            e["findings"] += 1
            e["versions"].add(f.version_id)
            if len(e["examples"]) < 3:
                e["examples"].append({"draft_id": f.version.draft_id, "title": f.version.draft.title, "quote": f.quote})
    recurring_out = sorted(({**{k: v for k, v in e.items() if k != "versions"}, "versions_affected": len(e["versions"]),
                             "versions_reviewed": len(reviewed_ids)} for e in recurring.values()),
                           key=lambda e: (-e["versions_affected"], -e["findings"]))

    # 2. Disagreement: decisions made in the period, with the reasons people recorded.
    dq = select(Finding).where(Finding.status.in_(["accepted", "edited", "dismissed", "overridden"]),
                               Finding.decided_at.is_not(None))
    if since:
        dq = dq.where(Finding.decided_at >= since)
    disagreement: dict[str, dict] = {}
    for f in db.scalars(dq):
        key, label = _label(f, rules)
        e = disagreement.setdefault(key, {"key": key, "label": label, "rule_key": rules[f.rule_id].key if f.rule_id in rules else None,
                                          "decided": 0, "fixed": 0, "dismissed": 0, "overridden": 0, "reasons": []})
        e["decided"] += 1
        e["fixed" if f.status in ("accepted", "edited") else f.status] += 1
        if f.status in ("dismissed", "overridden") and f.decision_reason:
            e["reasons"].append({"reason": f.decision_reason, "status": f.status, "draft_id": f.version.draft_id,
                                 "title": f.version.draft.title, "by": f.decided_by.name if f.decided_by else None})
    disagreement_out = []
    for e in disagreement.values():
        disputed = e["dismissed"] + e["overridden"]
        enough = e["decided"] >= MIN_DECISIONS
        e.update(disputed=disputed, rate=round(disputed / e["decided"], 2) if enough else None, enough_data=enough)
        if enough and e["rate"] >= 0.5 and e["rule_key"]:
            e["recommendation"] = (f"Reviewers set aside {disputed} of {e['decided']} {e['rule_key']} findings. "
                                   f"Review the wording of {e['rule_key']}; BrandSentinel will not change it on its own.")
        e["reasons"] = e["reasons"][-5:]
        disagreement_out.append(e)
    disagreement_out.sort(key=lambda e: (-(e["rate"] or 0), -e["decided"]))

    # 3. Unresolved risk right now (not limited to the period).
    latest = (select(DraftVersion.draft_id, func.max(DraftVersion.number).label("n"))
              .group_by(DraftVersion.draft_id).subquery())
    current_versions = list(db.scalars(select(DraftVersion).join(
        latest, (latest.c.draft_id == DraftVersion.draft_id) & (latest.c.n == DraftVersion.number))))
    if viewer.role == "creator":
        current_versions = [v for v in current_versions if v.draft.created_by_id == viewer.id]
    today = settings.today()
    blocking, expired_deps = [], []
    for v in current_versions:
        d = v.draft
        if d.status == "rejected":
            continue
        open_blocking = [f for f in v.findings if f.status == "open" and f.blocking]
        if open_blocking:
            blocking.append({"draft_id": d.id, "title": d.title, "version": v.number, "status": d.status,
                             "open_blocking": len(open_blocking),
                             "critical": sum(1 for f in open_blocking if f.severity == "critical")})
        for c in db.scalars(select(Citation).where(Citation.version_id == v.id)):
            fact = c.fact
            if fact.status != "approved":
                expired_deps.append({"draft_id": d.id, "title": d.title, "fact": fact.label, "fact_key": fact.key,
                                     "problem": f"{fact.status}"})
            elif fact.valid_until and fact.valid_until < today:
                expired_deps.append({"draft_id": d.id, "title": d.title, "fact": fact.label, "fact_key": fact.key,
                                     "problem": f"expired {fact.valid_until:%d %b %Y}"})
    renewals = [{"signoff_id": s.id, "draft_id": s.draft_id, "title": db.get(Draft, s.draft_id).title,
                 "reason": s.renewal_reason}
                for s in db.scalars(select(SignOff).where(SignOff.status == "needs_renewal"))]
    blocking.sort(key=lambda b: (-b["critical"], -b["open_blocking"]))

    # 4. Fact freshness, from recorded validity dates.
    expired, expiring, open_ended = [], [], []
    for fact in db.scalars(select(Fact).where(Fact.status == "approved").order_by(Fact.key)):
        if viewer.is_agency and fact.sensitivity != "public":
            continue
        row = {"key": fact.key, "label": fact.label, "metric": fact.metric,
               "valid_until": fact.valid_until.isoformat() if fact.valid_until else None}
        if fact.valid_until is None:
            open_ended.append(row)
        elif fact.valid_until < today:
            expired.append({**row, "days": (today - fact.valid_until).days})
        elif (fact.valid_until - today).days <= EXPIRY_HORIZON_DAYS:
            expiring.append({**row, "days": (fact.valid_until - today).days})
    expiring.sort(key=lambda r: r["days"])

    actions = []
    for r in expired:
        actions.append({"severity": "high", "text": f"{r['label']} expired {r['days']} day(s) ago; renew or replace it.",
                        "link": {"type": "fact", "key": r["key"]}})
    for r in expiring:
        actions.append({"severity": "medium", "text": f"{r['label']} expires in {r['days']} day(s) ({r['valid_until']}); "
                                                      "renew or replace it before then.", "link": {"type": "fact", "key": r["key"]}})
    for e in disagreement_out:
        if e.get("recommendation"):
            actions.append({"severity": "medium", "text": e["recommendation"], "link": {"type": "rule", "key": e["rule_key"]}})
    for s in renewals:
        actions.append({"severity": "high", "text": f"Sign-off of “{s['title']}” needs renewal: {s['reason']}.",
                        "link": {"type": "draft", "id": s["draft_id"]}})
    for b in blocking[:5]:
        actions.append({"severity": "high" if b["critical"] else "medium",
                        "text": f"“{b['title']}” v{b['version']} has {b['open_blocking']} open blocking finding(s).",
                        "link": {"type": "draft", "id": b["draft_id"]}})
    order = {"high": 0, "medium": 1}
    actions.sort(key=lambda a: order[a["severity"]])

    return {
        "period": {"days": days, "since": since.isoformat() if since else None, "until": now.isoformat(),
                   "versions_reviewed": len(reviewed_ids),
                   "drafts_reviewed": len({v.draft_id for v in reviewed})},
        "recurring": recurring_out,
        "disagreement": disagreement_out,
        "open_risk": {"blocking": blocking, "renewals": renewals, "stale_dependencies": expired_deps},
        "freshness": {"expired": expired, "expiring": expiring, "no_end_date": open_ended,
                      "horizon_days": EXPIRY_HORIZON_DAYS, "today": today.isoformat()},
        "actions": actions,
        "notes": [
            "Counts come from stored reviews and decisions; seeded demo drafts are included.",
            f"Disagreement rates are shown only for checks with at least {MIN_DECISIONS} decisions.",
        ],
    }
