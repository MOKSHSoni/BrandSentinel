"""The review pipeline without persistence: gateway, rules, claims, AI judge, checked corrections."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from ..models import Fact, Rule
from . import llm
from .claims import Claim, extract_claims
from .gateway import max_tier
from .rules import RuleHit, run_rule_checks
from .text import sentence_at
from .verify import Verdict, verify_claim

CLAIM_SEVERITY = {
    "contradicted": ("critical", True),
    "unverified": ("major", True),
    "needs_review": ("major", True),
    "supported": ("info", False),
}


@dataclass
class FindingDraft:
    check: str
    outcome: str
    severity: str
    blocking: bool
    start: int
    end: int
    quote: str
    message: str
    explanation: str = ""
    claim: dict | None = None
    fact: Fact | None = None
    rule: Rule | None = None
    candidates: list[Fact] = field(default_factory=list)
    suggestion: str | None = None
    fix_start: int | None = None
    fix_end: int | None = None
    correction_check: dict | None = None
    source: str = "rule"
    confidence: float | None = None


@dataclass
class Analysis:
    findings: list[FindingDraft]
    citations: dict[int, str]  # fact id -> strongest relation
    effective_tier: str
    ai_status: str
    model_errors: list[str] = field(default_factory=list)


def _overlap(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and b0 < a1


def _removal_fix(text: str, start: int, end: int) -> tuple[int, int, str] | None:
    """Remove an appositive claim ('X, trusted by...') only where the sentence stays grammatical."""
    sent = sentence_at(text, start)
    if text[end : end + 2] == ", ":
        fix_end = end + 2
        if start == sent.start and fix_end < len(text):
            return start, fix_end + 1, text[fix_end].upper()
        return start, fix_end, ""
    if text[max(0, start - 2) : start] == ", " and (end >= sent.end or text[end] in ".!?"):
        return start - 2, end, ""
    for dash in (" — ", " – ", " - "):
        if text[max(0, start - len(dash)) : start] == dash and (end >= sent.end or text[end] in ".!?,"):
            return start - len(dash), end, ""
    return None


def _merge_relation(citations: dict[int, str], rel: dict[int, str]) -> None:
    rank = {"compared": 0, "contradicted": 1, "supported": 2}
    for fid, r in rel.items():
        if rank.get(r, 0) >= rank.get(citations.get(fid, ""), -1):
            citations[fid] = r


def claim_findings(text: str, claims: list[Claim], facts: list[Fact], today: date, default_scope: str,
                   citations: dict[int, str]) -> list[FindingDraft]:
    out = []
    for c in claims:
        v: Verdict = verify_claim(c, facts, text, today, default_scope)
        _merge_relation(citations, v.relation)
        severity, blocking = CLAIM_SEVERITY[v.outcome]
        f = FindingDraft(
            check="claim", outcome=v.outcome, severity=severity, blocking=blocking, start=c.start, end=c.end,
            quote=text[c.start : c.end], message=v.message, explanation=v.explanation, claim=c.to_dict(),
            fact=v.fact, candidates=v.candidates, source=c.source,
        )
        if v.outcome == "contradicted" and v.replacement:
            f.suggestion, f.fix_start, f.fix_end = v.replacement, c.start, c.end
        elif v.outcome == "unverified" and c.kind in ("ranking", "comparison", "award", "testimonial"):
            fix = _removal_fix(text, c.start, c.end)
            if fix:
                f.fix_start, f.fix_end, f.suggestion = fix
        if c.source != "rule" and v.outcome != "supported":
            # Model-only claims are low precision: shown as suggestions until an admin makes them blocking.
            f.severity, f.blocking, f.outcome = "minor", False, "needs_review"
        out.append(f)
    return out


def rule_findings(text: str, hits: list[RuleHit]) -> list[FindingDraft]:
    out = []
    for h in hits:
        f = FindingDraft(
            check=h.check, outcome=h.outcome, severity=h.severity, blocking=h.blocking, start=h.start, end=h.end,
            quote=text[h.start : h.end], message=h.message, explanation=h.explanation, rule=h.rule,
        )
        if h.replacement is not None:
            f.suggestion = h.replacement
            f.fix_start = h.fix_start if h.fix_start is not None else h.start
            f.fix_end = h.fix_end if h.fix_end is not None else h.end
        out.append(f)
    return out


def check_correction(text: str, f: FindingDraft, replacement: str, fix_start: int, fix_end: int,
                     facts: list[Fact], rules: list[Rule], today: date, default_scope: str) -> dict:
    """Checks (a) and (b) of the three-way correction check. (c), the goal, is judged separately."""
    new_text = text[:fix_start] + replacement + text[fix_end:]
    r0, r1 = fix_start, fix_start + len(replacement)
    if r1 == r0:  # pure removal: inspect the joined area
        r0, r1 = max(0, r0 - 1), min(len(new_text), r1 + 1)

    new_claims = [c for c in extract_claims(new_text) if _overlap(c.start, c.end, r0, r1)]
    verdicts = [(c, verify_claim(c, facts, new_text, today, default_scope)) for c in new_claims]
    bad = [(c, v) for c, v in verdicts if v.outcome != "supported"]
    cited = sorted({v.fact.label for _, v in verdicts if v.fact})
    if bad:
        a = {"pass": False, "detail": f"“{bad[0][0].text}” would be {bad[0][1].outcome.replace('_', ' ')}."}
    elif cited:
        a = {"pass": True, "detail": "Supported by " + ", ".join(cited) + "."}
    elif f.rule is not None:
        a = {"pass": True, "detail": f"Uses the approved wording from {f.rule.key}; introduces no new claim."}
    else:
        a = {"pass": True, "detail": "Introduces no new claim."}

    # Only problems the fix leaves or introduces count; other issues in the sentence have their own findings.
    old_keys = {(h.check, text[h.start:h.end]) for h in run_rule_checks(text, rules)}
    new_hits = [h for h in run_rule_checks(new_text, rules) if _overlap(h.start, h.end, r0, r1)
                and (h.check == f.check or (h.blocking and (h.check, new_text[h.start:h.end]) not in old_keys))]
    same_claim_left = f.check == "claim" and any(
        v.outcome == f.outcome and c.text == f.quote for c, v in verdicts)
    if new_hits:
        b = {"pass": False, "detail": f"The corrected text still triggers: {new_hits[0].message}"}
    elif same_claim_left or (f.check == "claim" and bad):
        b = {"pass": False, "detail": "The corrected text still contains the problem claim."}
    else:
        b = {"pass": True, "detail": "Re-running the checks on the corrected text finds no violation here."}
    return {"supported": a, "removes_violation": b}


def _sentence_after(text: str, fix_start: int, fix_end: int, replacement: str) -> tuple[str, str]:
    sent = sentence_at(text, fix_start)
    s0, s1 = sent.start, max(sent.end, fix_end)
    before = text[s0:s1]
    after = text[s0:fix_start] + replacement + text[fix_end:s1]
    return before, after


def analyse(text: str, facts: list[Fact], rules: list[Rule], *, goal: str, draft_tier: str, today: date,
            default_scope: str, ai_factory: Callable[[str], llm.AIContext] | None) -> Analysis:
    citations: dict[int, str] = {}
    hits = run_rule_checks(text, rules)
    findings = rule_findings(text, hits)

    # Effective sensitivity: the highest tier of anything in the request. Codenames make it restricted.
    tier = draft_tier
    if any(h.check == "confidential" and h.rule is not None for h in hits):
        tier = max_tier(tier, "restricted")
    elif any(h.check == "confidential" for h in hits):
        tier = max_tier(tier, "confidential")
    ai = ai_factory(tier) if ai_factory else None

    # A banned phrase such as "100% safe" is reported once, by its rule, not again as a claim.
    claims = [c for c in extract_claims(text)
              if not any(_overlap(c.start, c.end, h.start, h.end) for h in hits if h.check in ("banned_phrase", "confidential"))]
    tone_rule = next((r for r in rules if r.kind == "tone" and r.status == "active"), None)

    model_claims, tone_issues = [], []
    if ai and ai.enabled:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_claims = pool.submit(llm.llm_extract_claims, ai, text)
            fut_tone = pool.submit(llm.llm_judge_tone, ai, text, tone_rule.guideline) if tone_rule else None
            model_claims = fut_claims.result()
            tone_issues = fut_tone.result() if fut_tone else []

    for mc in model_claims:
        start = text.find(mc.quote)
        end = start + len(mc.quote)
        if start < 0 or any(_overlap(start, end, c.start, c.end) for c in claims):
            continue
        if any(_overlap(start, end, h.start, h.end) for h in hits):
            continue
        claims.append(Claim(kind="other", start=start, end=end, text=mc.quote, source=ai.source_label,
                            extra={"model_type": mc.type}))
    findings += claim_findings(text, sorted(claims, key=lambda c: c.start), facts, today, default_scope, citations)

    for t in tone_issues:
        start = text.find(t.quote)
        end = start + len(t.quote)
        # The model judges tone only; anything touching a claim or an existing tone hit is dropped.
        if t.confidence < 0.6 or any(_overlap(start, end, f.start, f.end) for f in findings
                                     if f.check in ("tone", "claim")):
            continue
        findings.append(FindingDraft(
            check="tone", outcome="suggestion", severity="minor", blocking=False, start=start, end=end,
            quote=t.quote, message=t.issue, explanation=f"Guideline ({tone_rule.key}): {tone_rule.guideline}",
            rule=tone_rule, source=ai.source_label, confidence=round(t.confidence, 2),
        ))

    # Three-way correction check.
    goal_queue = []
    for i, f in enumerate(findings):
        if f.suggestion is None or f.fix_start is None:
            continue
        cc = check_correction(text, f, f.suggestion, f.fix_start, f.fix_end, facts, rules, today, default_scope)
        cc["before"], cc["after"] = _sentence_after(text, f.fix_start, f.fix_end, f.suggestion)
        if ai and ai.blocked_terms(f.suggestion):
            cc["removes_violation"] = {"pass": False, "detail": "The suggestion would insert a confidential term."}
        if f.check in ("claim", "confidential", "competitor", "banned_phrase"):
            cc["serves_goal"] = {"pass": None, "detail": "Waiting for the goal check."}
            if cc["supported"]["pass"] and cc["removes_violation"]["pass"]:
                goal_queue.append({"id": i, "before": cc["before"], "after": cc["after"]})
        else:
            cc["serves_goal"] = {"pass": True, "detail": "Wording-only fix; what the sentence says is unchanged."}
        f.correction_check = cc

    goal_results = llm.llm_check_goals(ai, goal, goal_queue) if (ai and ai.enabled and goal_queue) else {}
    for i, f in enumerate(findings):
        cc = f.correction_check
        if not cc:
            continue
        if cc["serves_goal"]["pass"] is None:
            r = goal_results.get(i)
            if r is not None:
                cc["serves_goal"] = {"pass": r.serves_goal, "detail": r.reason}
            elif cc["supported"]["pass"] and cc["removes_violation"]["pass"]:
                cc["serves_goal"] = {"pass": None, "detail": "No model available: the reviewer confirms the goal is still served."}
            else:
                cc["serves_goal"] = {"pass": None, "detail": "Not checked because an earlier check failed."}
        cc["shown"] = bool(cc["supported"]["pass"] and cc["removes_violation"]["pass"] and cc["serves_goal"]["pass"] is not False)
        if not cc["shown"]:
            cc["withheld"] = f.suggestion
            f.suggestion = None

    if ai is None:
        ai_status = "AI judge off for this run (rules only)."
    elif ai.enabled:
        where = "local model" if ai.route.location == "local" else "external model"
        ai_status = f"AI judge: {where}. {ai.route.reason}"
        if ai.errors:
            ai_status += f" {len(ai.errors)} model call(s) failed; rule results are unaffected."
    else:
        ai_status = f"AI judge skipped: {ai.route.reason} Rule checks and claim verification ran in full."

    findings.sort(key=lambda f: (f.start, f.end))
    return Analysis(findings, citations, tier, ai_status, ai.errors if ai else [])


def apply_fixes(text: str, fixes: list[tuple[int, int, str]]) -> str:
    """Apply non-overlapping replacements from the end so earlier offsets stay valid."""
    taken: list[tuple[int, int]] = []
    for s, e, r in sorted(fixes, key=lambda x: x[0], reverse=True):
        if any(_overlap(s, e, a, b) or (s == e and a <= s <= b) for a, b in taken):
            continue
        text = text[:s] + r + text[e:]
        taken.append((s, e))
    return re.sub(r"[ \t]{2,}", " ", text)
