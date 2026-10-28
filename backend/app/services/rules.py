"""Deterministic rule checks. Each hit cites the rule and quotes its guideline."""

import re
from dataclasses import dataclass, field

from ..models import Rule
from .text import find_phrase, sentence_at

PII_PATTERNS = {
    "PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "Aadhaar": re.compile(r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b"),
    "GSTIN": re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b"),
    "Phone": re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)"),
    "Email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
}
INJECTION_RE = re.compile(
    r"ignore (?:all |any )?(?:previous|prior|above) instructions|disregard (?:the )?(?:rules|instructions)|"
    r"you are now|system prompt|mark (?:this|everything) as (?:approved|supported)|approve this draft",
    re.I,
)
# Acronyms allowed in capitals when the tone check looks for shouting.
ACRONYMS = {"UPI", "PIN", "KYC", "RBI", "NPCI", "OTP", "EMI", "GST", "PAN", "ATM", "QR", "PCI", "DSS", "ISO", "FAQ", "APP", "T&C", "NEFT", "IMPS", "SMS"}


@dataclass
class RuleHit:
    check: str
    rule: Rule | None
    start: int
    end: int
    message: str
    explanation: str
    severity: str
    blocking: bool
    outcome: str = "violation"  # violation | suggestion | needs_review
    replacement: str | None = None
    fix_start: int | None = None
    fix_end: int | None = None
    extra: dict = field(default_factory=dict)


def _variant_regex(correct: str) -> re.Pattern:
    words = [re.escape(w) for w in re.split(r"[\s\-]+", correct) if w]
    return re.compile(r"(?<![\w])" + r"[\s\-]*".join(words) + r"(?![\w])", re.I)


def check_terminology(text: str, rule: Rule) -> list[RuleHit]:
    cfg = rule.config
    correct = cfg["correct"]
    hits, seen = [], set()
    for m in _variant_regex(correct).finditer(text):
        if m.group(0) != correct:
            seen.add(m.start())
            hits.append(RuleHit("terminology", rule, m.start(), m.end(),
                                f"Use “{correct}”, not “{m.group(0)}”.", rule.guideline, rule.severity, rule.blocking,
                                replacement=correct))
    for variant in cfg.get("variants", []):
        flags = 0 if cfg.get("case_sensitive_variants") else re.I
        for m in re.finditer(r"(?<![\w])" + re.escape(variant) + r"(?![\w])", text, flags):
            if m.start() in seen or m.group(0) == correct:
                continue
            seen.add(m.start())
            hits.append(RuleHit("terminology", rule, m.start(), m.end(),
                                f"Use “{correct}”, not “{m.group(0)}”.", rule.guideline, rule.severity, rule.blocking,
                                replacement=correct))
    return hits


def check_terms(text: str, rule: Rule, check: str, outcome: str = "violation") -> list[RuleHit]:
    cfg = rule.config
    hits = []
    for term in cfg.get("terms", []):
        start = 0
        while (m := find_phrase(text, term, start)) is not None:
            replacement = cfg.get("replacements", {}).get(term, cfg.get("replacement"))
            hits.append(RuleHit(check, rule, m.start(), m.end(),
                                cfg.get("message", "“{term}” is not allowed.").format(term=m.group(0)),
                                rule.guideline, rule.severity, rule.blocking, outcome=outcome,
                                replacement=replacement))
            start = m.end()
    return hits


def check_disclaimer(text: str, rule: Rule) -> list[RuleHit]:
    cfg = rule.config
    trigger = re.compile(cfg["trigger_regex"], re.I)
    present = re.compile(cfg["present_regex"], re.I)
    m = trigger.search(text)
    if not m or present.search(text):
        return []
    sent = sentence_at(text, m.start())
    sentence = text[sent.start : sent.end]
    stripped = sentence.rstrip()
    fixed = stripped + ("" if stripped.endswith((".", "!", "?")) else ".") + " " + cfg["required"] + "."
    return [RuleHit("disclaimer", rule, m.start(), m.end(),
                    f"“{m.group(0)}” needs the disclaimer “{cfg['required']}”.",
                    rule.guideline, rule.severity, rule.blocking,
                    replacement=fixed, fix_start=sent.start, fix_end=sent.start + len(stripped))]


def check_tone(text: str, rule: Rule) -> list[RuleHit]:
    hits = check_terms(text, rule, "tone", outcome="suggestion")
    for h in hits:
        h.message = f"“{text[h.start:h.end]}” reads as hype or fear-based urgency."
    for m in re.finditer(r"!{2,}", text):
        hits.append(RuleHit("tone", rule, m.start(), m.end(), "Stacked exclamation marks.",
                                rule.guideline, rule.severity, False, outcome="suggestion", replacement="."))
    for m in re.finditer(r"\b[A-Z]{4,}\b", text):
        if m.group(0) in ACRONYMS:
            continue
        hits.append(RuleHit("tone", rule, m.start(), m.end(), f"“{m.group(0)}” is written in capitals (shouting).",
                            rule.guideline, rule.severity, False, outcome="suggestion",
                            replacement=m.group(0).capitalize()))
    return hits


def check_confidential(text: str, rules: list[Rule]) -> list[RuleHit]:
    hits = []
    for rule in rules:
        hits += check_terms(text, rule, "confidential")
    for label, rx in PII_PATTERNS.items():
        if label == "Email" and re.search(r"@nimbuspay\.(?:example|in|com)\b", text):
            continue
        for m in rx.finditer(text):
            if label == "Email" and m.group(0).lower().endswith(("nimbuspay.example", "nimbuspay.in")):
                continue
            hits.append(RuleHit("confidential", None, m.start(), m.end(),
                                f"Personal data detected ({label}).",
                                "Personal identifiers such as PAN, Aadhaar, GSTIN, phone numbers and personal "
                                "e-mail addresses must not appear in marketing drafts or be sent to external models.",
                                "critical", True, extra={"pii": label}))
    return hits


def check_injection(text: str) -> list[RuleHit]:
    return [RuleHit("injection", None, m.start(), m.end(), "Text that looks like instructions to an AI system.",
                    "Drafts are treated as data. Instructions inside a draft are ignored by the AI judge; a reviewer "
                    "should check why they are there.", "major", False, outcome="needs_review")
            for m in INJECTION_RE.finditer(text)]


def run_rule_checks(text: str, rules: list[Rule]) -> list[RuleHit]:
    hits: list[RuleHit] = []
    active = [r for r in rules if r.status == "active"]
    for rule in active:
        if rule.kind == "terminology":
            hits += check_terminology(text, rule)
        elif rule.kind == "competitor":
            hits += check_terms(text, rule, "competitor")
        elif rule.kind == "banned_phrase":
            hits += check_terms(text, rule, "banned_phrase")
        elif rule.kind == "disclaimer":
            hits += check_disclaimer(text, rule)
        elif rule.kind == "tone":
            hits += check_tone(text, rule)
    hits += check_confidential(text, [r for r in active if r.kind == "confidential_term"])
    hits += check_injection(text)
    # Drop exact duplicates (same check and span).
    unique: dict[tuple, RuleHit] = {}
    for h in hits:
        unique.setdefault((h.check, h.start, h.end), h)
    return sorted(unique.values(), key=lambda h: h.start)
