"""Brand Impact Simulator: what a proposed fact or rule change would do, computed without writing anything.

The proposal is built as transient (never added to the session) Fact/Rule objects, and every affected draft is
re-verified twice, against the current ledger and against the proposal, so the before/after comparison uses the
same code as a real review. The session is rolled back at the end as a second guard.
"""

import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Draft, DraftVersion, Fact, Rule, SignOff, User
from ..serializers import can_see
from . import images
from .analysis import image_findings
from .claims import extract_claims
from .governance import FACT_FIELDS, GovernanceError, affected_by
from .numbers import format_value
from .review import ledger
from .rules import run_rule_checks
from .verify import verify_claim

PROPOSED_ID = -1


def proposed_fact(old: Fact, changes: dict) -> tuple[Fact, Fact]:
    """(old as it would look once superseded, the proposed new version), both transient."""
    data = {k: getattr(old, k) for k in FACT_FIELDS}
    data.update({k: v for k, v in changes.items() if k in FACT_FIELDS and v is not None})
    if changes.get("value_num") is not None and "value_text" not in changes:
        data["value_text"] = format_value(float(changes["value_num"]), data["kind"])
    if data["value_text"] != old.value_text and "statement" not in changes and old.value_text in (old.statement or ""):
        data["statement"] = old.statement.replace(old.value_text, data["value_text"])
    if "effective_date" not in changes:
        data["effective_date"] = settings.today()
    new = Fact(id=PROPOSED_ID, key=old.key, version=old.version + 1, status="approved", supersedes_id=old.id, **data)
    old_copy = Fact(id=old.id, key=old.key, version=old.version, status="superseded", superseded_by_id=PROPOSED_ID,
                    supersedes_id=old.supersedes_id, **{k: getattr(old, k) for k in FACT_FIELDS})
    # Transient objects get no column defaults, so set the text fields the checks read.
    new.change_note = changes.get("note", "") or ""
    old_copy.change_note = "proposed change (not yet approved)"
    return old_copy, new


def _verdict_view(v, viewer: User) -> dict:
    f = v.fact
    hidden = f is not None and not can_see(viewer, f)
    return {"outcome": v.outcome, "fact": f.label if f else None,
            "message": f"Checked against approved fact {f.label} (internal)." if hidden else v.message}


def _valid_signoff(db: Session, version_id: int) -> SignOff | None:
    return db.scalar(select(SignOff).where(SignOff.version_id == version_id, SignOff.status == "valid"))


def simulate_fact(db: Session, old: Fact, changes: dict, viewer: User, retract: bool = False) -> dict:
    t0 = time.perf_counter()
    if old.status != "approved":
        raise GovernanceError(f"{old.label} is {old.status}; only the current approved version can be changed.")
    facts, _ = ledger(db)
    old_copy, new = proposed_fact(old, changes)
    if retract:
        old_copy.status, old_copy.superseded_by_id = "retracted", None
        hypothetical = [f for f in facts if f.id != old.id] + [old_copy]
    else:
        hypothetical = [f for f in facts if f.id != old.id] + [old_copy, new]
    today, scope = settings.today(), settings.brand_default_scope

    drafts, transitions = [], {}
    a = affected_by(db, [old.id])
    for v, _fact_id, relation in a["current"]:
        text = images.mask_headers(v.content)
        rows = []
        for c in extract_claims(text):
            before = verify_claim(c, facts, text, today, scope)
            after = verify_claim(c, hypothetical, text, today, scope)
            involved = old.id in before.relation or PROPOSED_ID in after.relation or old.id in after.relation \
                or (before.fact is not None and before.fact.id == old.id)
            if not involved:
                continue
            changed = before.outcome != after.outcome
            if changed:
                key = f"{before.outcome} → {after.outcome}"
                transitions[key] = transitions.get(key, 0) + 1
            rows.append({"quote": text[c.start:c.end], "before": _verdict_view(before, viewer),
                         "after": _verdict_view(after, viewer), "changed": changed})
        signoff = _valid_signoff(db, v.id)
        d = v.draft
        if any(r["changed"] for r in rows):
            reason = "Re-review would change the outcome of the claims below."
        elif relation == "compared":
            reason = (f"Cites {old.label} only as a candidate (a related or ambiguous metric), so the outcome "
                      "would not change; it is still flagged because it relied on the old version.")
        else:
            reason = "Outcome would not change, but the draft relied on the old version, so it is flagged for re-review."
        drafts.append({"draft_id": d.id, "title": d.title, "version": v.number, "status": d.status,
                       "relation": relation, "signed_off": signoff is not None, "claims": rows, "reason": reason})
    drafts.sort(key=lambda x: (not any(r["changed"] for r in x["claims"]), x["title"]))
    db.rollback()  # nothing above is persisted; this guarantees it
    visible_new = can_see(viewer, new)
    return {
        "read_only": True,
        "fact": {"key": old.key, "from": {"label": old.label, "value_text": old.value_text, "scope": old.scope,
                                          "effective_date": old.effective_date.isoformat()},
                 "to": None if retract else {"label": f"{old.key} v{new.version}",
                                             "value_text": new.value_text if visible_new else "(internal)",
                                             "scope": new.scope, "effective_date": new.effective_date.isoformat()}},
        "retract": retract,
        "drafts": drafts,
        "expected_draft_ids": sorted(x["draft_id"] for x in drafts),
        "signoffs_to_renew": sum(1 for x in drafts if x["signed_off"]),
        "outcome_changes": transitions,
        "drafts_with_changes": sum(1 for x in drafts if any(r["changed"] for r in x["claims"])),
        "historic_versions": a["historic_versions"],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


RULE_FIELDS = ("kind", "name", "guideline", "severity", "blocking", "config", "status", "sensitivity")


def _rule_hits(text: str, assets: list, rule: Rule | None) -> dict:
    if rule is None or rule.status != "active":
        return {}
    if rule.kind in ("accessibility", "palette"):
        hits = [(f.check, f.start, f.end, f.message, f.blocking, f.severity) for f in image_findings(text, assets, [rule])]
    else:
        masked = images.mask_headers(text)
        hits = [(h.check, h.start, h.end, h.message, h.blocking, h.severity)
                for h in run_rule_checks(masked, [rule]) if h.rule is not None and h.rule.key == rule.key]
    return {(c, s, e): {"quote": text[s:e], "message": m, "blocking": b, "severity": sev} for c, s, e, m, b, sev in hits}


def simulate_rule(db: Session, rule: Rule, changes: dict) -> dict:
    t0 = time.perf_counter()
    data = {k: getattr(rule, k) for k in RULE_FIELDS}
    data.update({k: v for k, v in changes.items() if k in RULE_FIELDS and v is not None})
    proposed = Rule(id=rule.id, key=rule.key, version=rule.version + 1, **data)
    latest = (select(DraftVersion.draft_id, func.max(DraftVersion.number).label("n"))
              .group_by(DraftVersion.draft_id).subquery())
    versions = db.scalars(select(DraftVersion).join(
        latest, (latest.c.draft_id == DraftVersion.draft_id) & (latest.c.n == DraftVersion.number)))
    drafts = []
    totals = {"new": 0, "removed": 0, "now_blocking": 0, "no_longer_blocking": 0}
    for v in versions:
        before = _rule_hits(v.content, v.assets or [], rule)
        after = _rule_hits(v.content, v.assets or [], proposed)
        rows = []
        for k in after.keys() - before.keys():
            rows.append({"change": "new", **after[k]})
        for k in before.keys() - after.keys():
            rows.append({"change": "removed", **before[k]})
        for k in after.keys() & before.keys():
            if after[k]["blocking"] != before[k]["blocking"]:
                rows.append({"change": "now_blocking" if after[k]["blocking"] else "no_longer_blocking", **after[k]})
            elif after[k]["severity"] != before[k]["severity"]:
                rows.append({"change": "severity", **after[k], "was": before[k]["severity"]})
        for r in rows:
            if r["change"] in totals:
                totals[r["change"]] += 1
        if rows:
            d = v.draft
            drafts.append({"draft_id": d.id, "title": d.title, "version": v.number, "status": d.status,
                           "changes": sorted(rows, key=lambda r: r["change"])})
    renewals = list(db.scalars(select(SignOff).where(SignOff.status == "valid")))
    db.rollback()
    return {
        "read_only": True,
        "rule": {"key": rule.key, "name": rule.name, "from_version": rule.version, "to_version": rule.version + 1},
        "drafts": sorted(drafts, key=lambda x: x["title"]),
        "totals": totals,
        "signoffs_to_renew": [{"signoff_id": s.id, "draft_id": s.draft_id,
                               "draft_title": db.get(Draft, s.draft_id).title} for s in renewals],
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
    }
