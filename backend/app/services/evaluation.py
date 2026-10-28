"""Measured reliability: run a labelled test set through the pipeline (and baselines) and count hits.

Results are reported as counts ("17 of 20 caught"), per category and severity, against the targets in the plan.
"""

import json
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from ..config import settings
from ..models import Fact, Rule
from . import llm
from .analysis import analyse
from .gateway import Masker, route_request

DATASET = Path(__file__).resolve().parents[2] / "eval" / "dataset.json"
EVAL_DATE = date(2026, 10, 27)

SEVERITY = {
    "claim_contradicted": "critical", "confidential": "critical", "banned_phrase": "critical",
    "claim_unverified": "major", "claim_needs_review": "major", "terminology": "major", "competitor": "major",
    "disclaimer": "major", "injection": "major", "tone": "minor",
}
TARGETS = {"critical": {"recall": 0.95}, "major": {"precision": 0.90, "recall": 0.90}, "minor": {}}
CATEGORIES = list(SEVERITY) + ["claim_supported"]


class BaselineItem(BaseModel):
    quote: str
    category: str
    fact_id: str | None = None


class BaselineList(BaseModel):
    findings: list[BaselineItem] = Field(default_factory=list)


def seeded_ledger() -> tuple[list[Fact], list[Rule]]:
    """The labelled set is written against the seed ledger, so score against a fresh copy of it."""
    from sqlalchemy.orm import sessionmaker

    from ..db import Base, make_engine
    from ..seed import seed
    from .review import ledger

    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    seed(db, with_drafts=False)
    facts, rules = ledger(db)
    db.close()
    return facts, rules


def load_dataset() -> list[dict]:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def category(check: str, outcome: str) -> str:
    return f"claim_{outcome}" if check == "claim" else check


def predict_pipeline(text: str, facts: list[Fact], rules: list[Rule], use_ai: bool) -> list[dict]:
    factory = None
    if use_ai:
        def factory(tier: str):
            route = route_request(tier, llm.local_available(), llm.external_available(), [])
            return llm.AIContext(route=route, tier=tier, masker=Masker([]), confidential_terms=[], log=lambda **kw: None)
    a = analyse(text, facts, rules, goal="", draft_tier="public", today=EVAL_DATE,
                default_scope=settings.brand_default_scope, ai_factory=factory)
    return [{"cat": category(f.check, f.outcome), "start": f.start, "end": f.end, "fact": f.fact.key if f.fact else None,
             "suggestion": f.suggestion, "cc": f.correction_check}
            for f in a.findings]


def _guide(rules: list[Rule], facts: list[Fact], structured: bool) -> str:
    lines = ["Nimbus Pay brand guide (fictional UPI payments app, India).", "Rules:"]
    lines += [f"- {r.name}: {r.guideline}" + (f" Terms: {', '.join(r.config.get('terms', []))}." if r.config.get("terms") else "")
              for r in rules]
    current = [f for f in facts if f.status == "approved"]
    if structured:
        lines.append("Approved facts (JSON, with versions; superseded versions apply only to their dates):")
        lines.append(json.dumps([{"id": f.key, "version": f.version, "status": f.status, "metric": f.metric,
                                  "value": f.value_text, "scope": f.scope, "effective": f.effective_date.isoformat(),
                                  "valid_until": f.valid_until.isoformat() if f.valid_until else None} for f in facts]))
    else:
        lines.append("About us: " + " ".join(f"{f.statement}." for f in current if f.statement))
    return "\n".join(lines)


def predict_baseline(text: str, facts: list[Fact], rules: list[Rule], structured: bool) -> list[dict]:
    route = route_request("public", llm.local_available(), llm.external_available(), [])
    ctx = llm.AIContext(route=route, tier="public", masker=Masker([]), confidential_terms=[], log=lambda **kw: None)
    cats = ", ".join(CATEGORIES)
    out = ctx.ask(
        "baseline",
        _guide(rules, facts, structured) + "\n\nReview the draft against this brand guide. Report every problem and "
        f"every factual claim. Use one category per item from: {cats}. claim_supported means a claim the facts confirm. "
        'Schema: {"findings": [{"quote": "<exact substring>", "category": "<category>", "fact_id": "<F-xx or null>"}]}',
        llm.wrap(text),
        BaselineList,
    )
    preds = []
    for item in (out.findings if out else []):
        start = text.find(item.quote)
        if start < 0 or item.category not in CATEGORIES:
            continue
        preds.append({"cat": item.category, "start": start, "end": start + len(item.quote), "fact": item.fact_id,
                      "suggestion": None, "cc": None})
    return preds



def _span(text: str, quote: str) -> tuple[int, int]:
    i = text.find(quote)
    if i < 0:
        raise ValueError(f"Expected quote not in text: {quote!r}")
    return i, i + len(quote)


def score(dataset: list[dict], predictions: dict[str, list[dict]]) -> dict:
    per_cat = {c: {"tp": 0, "fp": 0, "fn": 0} for c in CATEGORIES}
    evidence = {"correct": 0, "total": 0}
    flagged = {"caught": 0, "total": 0}  # any non-supported claim outcome on a problem claim
    clean_fp, clean_n = 0, 0
    misses, false_alarms = [], []
    for item in dataset:
        text, preds = item["text"], list(predictions[item["id"]])
        used = set()
        for e in item["expected"]:
            s, t = _span(text, e["quote"])
            match = next((i for i, p in enumerate(preds) if i not in used and p["cat"] == e["cat"]
                          and p["start"] < t and s < p["end"]), None)
            if e["cat"].startswith("claim_") and e["cat"] != "claim_supported":
                flagged["total"] += 1
                if any(p["cat"].startswith("claim_") and p["cat"] != "claim_supported" and p["start"] < t and s < p["end"]
                       for p in preds):
                    flagged["caught"] += 1
            if match is None:
                per_cat[e["cat"]]["fn"] += 1
                misses.append({"id": item["id"], "cat": e["cat"], "quote": e["quote"]})
                continue
            used.add(match)
            per_cat[e["cat"]]["tp"] += 1
            if e.get("fact"):
                evidence["total"] += 1
                if preds[match]["fact"] == e["fact"]:
                    evidence["correct"] += 1
        extra = [p for i, p in enumerate(preds) if i not in used and p["cat"] in per_cat]
        for p in extra:
            per_cat[p["cat"]]["fp"] += 1
            false_alarms.append({"id": item["id"], "cat": p["cat"], "quote": text[p["start"]:p["end"]]})
        if item["part"] == "clean":
            clean_n += 1
            clean_fp += sum(1 for p in extra if p["cat"] != "claim_supported")

    def pr(c):
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        return {**c, "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "recall": round(tp / (tp + fn), 3) if tp + fn else None}

    cats = {k: pr(v) for k, v in per_cat.items() if v["tp"] + v["fp"] + v["fn"]}
    sev = {}
    for level in ("critical", "major", "minor"):
        agg = {"tp": 0, "fp": 0, "fn": 0}
        for c, v in per_cat.items():
            if SEVERITY.get(c) == level:
                for k in agg:
                    agg[k] += v[k]
        res = pr(agg)
        target = TARGETS[level]
        res["target"] = target
        res["meets_target"] = all(res.get(m) is not None and res[m] >= goal for m, goal in target.items()) if target else None
        sev[level] = res
    flagged_checks = [c for c, v in cats.items() if SEVERITY.get(c) in ("critical", "major") and (
        (v["recall"] is not None and v["recall"] < TARGETS[SEVERITY[c]].get("recall", 0)) or
        (SEVERITY[c] == "major" and v["precision"] is not None and v["precision"] < 0.90))]
    return {
        "categories": cats, "severity": sev, "evidence": evidence, "problem_claims_flagged": flagged,
        "false_alarms_per_clean_draft": round(clean_fp / clean_n, 2) if clean_n else None, "clean_drafts": clean_n,
        "flagged_for_admin": flagged_checks, "misses": misses, "false_alarms": false_alarms,
    }


def corrections_summary(predictions: dict[str, list[dict]]) -> dict:
    offered = shown = 0
    for preds in predictions.values():
        for p in preds:
            if p["cc"]:
                offered += 1
                shown += 1 if p["cc"].get("shown") else 0
    return {"proposed": offered, "passed_all_checks": shown}


def run(mode: str, facts: list[Fact], rules: list[Rule], dataset: list[dict] | None = None) -> dict:
    dataset = dataset or load_dataset()
    preds, t0 = {}, time.time()
    for item in dataset:
        if mode == "pipeline_rules":
            preds[item["id"]] = predict_pipeline(item["text"], facts, rules, use_ai=False)
        elif mode == "pipeline_ai":
            preds[item["id"]] = predict_pipeline(item["text"], facts, rules, use_ai=True)
        elif mode == "llm_brand_guide":
            preds[item["id"]] = predict_baseline(item["text"], facts, rules, structured=False)
        elif mode == "llm_structured_facts":
            preds[item["id"]] = predict_baseline(item["text"], facts, rules, structured=True)
        else:
            raise ValueError(mode)
    result = score(dataset, preds)
    result["drafts"] = len(dataset)
    result["parts"] = {p: sum(1 for d in dataset if d["part"] == p) for p in sorted({d["part"] for d in dataset})}
    result["seconds"] = round(time.time() - t0, 1)
    result["mode"] = mode
    if mode.startswith("pipeline"):
        result["corrections"] = corrections_summary(preds)
    return result
