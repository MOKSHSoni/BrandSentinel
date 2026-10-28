"""Deterministic claim extraction: numbers, rankings, comparisons, awards, testimonials."""

import re
from dataclasses import asdict, dataclass, field
from datetime import date
import calendar

from .numbers import NUMBER_RE, QUALIFIERS, to_float
from .text import clause_at, sentence_at

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))

STOP = {
    "in", "across", "on", "at", "and", "with", "who", "that", "for", "from", "since", "as",
    "by", "to", "than", "every", "each", "per", "a", "an", "is", "are", "was", "were", "have",
    "has", "use", "using", "trust", "rely", "choose", "pay", "love", "this", "today", "now",
    "or", "but", "so", "via", "through", "within", "over", "under",
}
DURATION_UNITS = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "s": 1, "minute": 60, "minutes": 60,
                  "min": 60, "mins": 60, "hour": 3600, "hours": 3600}

SCOPES = {
    "india": "India", "mumbai": "Mumbai", "delhi": "Delhi", "bengaluru": "Bengaluru",
    "bangalore": "Bengaluru", "pune": "Pune", "chennai": "Chennai", "hyderabad": "Hyderabad",
    "kolkata": "Kolkata", "maharashtra": "Maharashtra", "karnataka": "Karnataka", "asia": "Asia",
    "south asia": "South Asia", "southeast asia": "Southeast Asia", "worldwide": "Global",
    "globally": "Global", "global": "Global", "the world": "Global", "world's": "Global",
    "google play": "Google Play", "play store": "Google Play", "app store": "App Store",
}
SCOPE_RE = re.compile(r"\b(" + "|".join(re.escape(s) for s in sorted(SCOPES, key=len, reverse=True)) + r")(?:'s)?\b", re.I)

RANK_WORDS = (
    r"#\s?1|no\.?\s?1|number\s+one|largest|biggest|leading|best(?:-in-class)?|"
    r"most\s+(?:trusted|loved|popular|secure|reliable|downloaded)|fastest(?:[- ]growing)?|"
    r"top[- ]rated|safest|cheapest|unbeatable|favou?rite"
)
RANK_RE = re.compile(
    r"(?:\b(?:[A-Z][a-z]+(?:\s[A-Z][a-z]+)?'s|[Tt]he|[Oo]ur|[Ww]orld's)\s+)?"
    r"(?:" + RANK_WORDS + r")(?![\w])"
    r"(?:[ \t]+(?!(?:in|across|for|to|with|and|by|on|at|of|that|who|since|is|are|was|has|have|serves|offers|lets|helps|makes|gives|trusted|used)\b)[A-Za-z&-]+){0,2}",
)
COMPARE_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?x\s+|twice\s+as\s+\w+\s+as\s+|(?:two|three|\d+)\s+times\s+)?"
    r"(?:faster|cheaper|safer|better|quicker|easier|simpler|more\s+\w+|lower\s+\w+)\s+than\s+[^.,;!?\n]{1,40}?(?=[.,;!?\n]|\s(?:and|with|for|so|but)\s|$)",
    re.I,
)
AWARD_RE = re.compile(
    r"\b(?:award[- ]winning(?:\s+\w+){0,2}|winner\s+of\s+[^.,;!?\n]{3,40}|"
    r"PCI[- ]DSS(?:\s+v?[\d.]+)?\s+certified|ISO\s+\d+\s+certified|RBI[- ](?:approved|authori[sz]ed)|"
    r"certified\s+by\s+[^.,;!?\n]{3,30})",
    re.I,
)
TESTIMONIAL_RE = re.compile(
    r"[\"“](?P<quote>[^\"”]{20,300})[\"”]\s*(?:[—–-]+\s*|,?\s*(?:said|says)\s+)(?P<who>[A-Z][a-z]+(?:\s[A-Z][a-z]*\.?)?)"
)
VAGUE_RE = re.compile(r"\b(?P<word>millions|lakhs|thousands|crores|hundreds)\s+of\s+(?P<metric>[a-z]+)", re.I)
VAGUE_VALUE = {"hundreds": 100, "thousands": 1_000, "lakhs": 100_000, "millions": 1_000_000, "crores": 10_000_000}
DATE_RE = re.compile(
    r"\b(?:in|as\s+of|as\s+at|during|by\s+end\s+of)\s+(?:(?P<day>\d{1,2})\s+)?(?:(?P<month>" + MONTH_RE + r")\.?\s+)?(?P<year>20\d{2})\b",
    re.I,
)


@dataclass
class Claim:
    kind: str  # count | percentage | money | rating | duration | ranking | comparison | award | testimonial | other
    start: int
    end: int
    text: str
    value: float | None = None
    value_text: str = ""
    num_start: int | None = None
    num_end: int | None = None
    qualifier: str = "exact"
    metric_phrase: str = ""
    context: str = ""
    unit: str = ""
    scope: str | None = None
    claim_date: str | None = None
    source: str = "rule"
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def find_scope(text: str, start: int, end: int) -> str | None:
    clause = clause_at(text, start, end)
    sent = sentence_at(text, start)
    for span in (clause, sent):
        m = SCOPE_RE.search(text, span.start, span.end)
        if m:
            return SCOPES[m.group(1).lower()]
    return None


def find_date(text: str, start: int) -> str | None:
    sent = sentence_at(text, start)
    m = DATE_RE.search(text, sent.start, sent.end)
    if not m:
        return None
    year = int(m.group("year"))
    month = MONTHS.get((m.group("month") or "").lower().rstrip("."))
    if month:
        day = int(m.group("day") or calendar.monthrange(year, month)[1])
        return date(year, month, min(day, calendar.monthrange(year, month)[1])).isoformat()
    return date(year, 12, 31).isoformat()


def _metric_after(text: str, pos: int, limit: int) -> tuple[str, int]:
    words, end = [], pos
    for m in re.finditer(r"[A-Za-z][\w'-]*|[^\sA-Za-z]", text[pos:limit]):
        token = m.group(0)
        if not token[0].isalpha():
            if words or token not in "-":
                break
            continue
        if token.lower() in STOP and (words or token.lower() not in ("of",)):
            break
        if token.lower() == "of" and not words:
            continue
        words.append(token)
        end = pos + m.end()
        if len(words) == 4:
            break
    return " ".join(words), end


def _is_noise_number(text: str, m: re.Match) -> bool:
    num = m.group("num")
    before = text[max(0, m.start() - 12) : m.start()].lower()
    after = text[m.end() : m.end() + 12].lower()
    if before.rstrip().endswith(("#", "no.", "no", "v", "version", "upi")) and not m.group("qual"):
        return True
    if re.match(r"\s*(?:" + MONTH_RE + r")\b", after) or re.search(r"(?:" + MONTH_RE + r")\.?\s*$", before):
        return True
    if re.match(r"\s*(?:am|pm|/7|/5|x\b|-star|th\b|st\b|nd\b|rd\b)", after) and "star" not in after:
        return True
    if text[max(0, m.start() - 1) : m.start()] == "/" or after.startswith("/"):
        return True
    plain = num.replace(",", "")
    if "," not in num and "." not in num and len(plain) == 4 and 1990 <= int(plain) <= 2099 and not m.group("cur"):
        return True
    if "," not in num and len(plain) >= 7 and not m.group("cur"):
        return True  # phone numbers, ids
    return False


def extract_numbers(text: str) -> list[Claim]:
    claims = []
    for m in NUMBER_RE.finditer(text):
        if _is_noise_number(text, m):
            continue
        qual_raw = (m.group("qual") or "").strip().lower()
        qualifier = QUALIFIERS.get(qual_raw, "exact")
        if m.group("plus"):
            qualifier = "at_least"
        value = to_float(m.group("num"), m.group("scale"))
        sent = sentence_at(text, m.start())
        clause = clause_at(text, m.start(), m.end())
        after = text[m.end() : sent.end]
        before = text[clause.start : m.start()].lower()
        rating_after = re.match(r"\s*(?:/\s*5|-?\s*stars?|\s*star rating)", after, re.I)
        dur = re.match(r"\s*(seconds?|secs?|s\b|minutes?|mins?|hours?)", after, re.I)

        if m.group("pct"):
            kind = "percentage"
        elif m.group("cur"):
            kind = "money"
        elif rating_after or re.search(r"\brated\s*$", before):
            kind = "rating"
        elif dur:
            kind = "duration"
            value *= DURATION_UNITS[dur.group(1).lower()]
        else:
            kind = "count"

        metric_from = m.end()
        if rating_after:
            metric_from += rating_after.end()
        elif dur:
            metric_from += dur.end()
        metric, metric_end = _metric_after(text, metric_from, sent.end)
        if kind == "duration":
            metric_end = metric_from
            metric = ""
        start = m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))
        rated = re.search(r"\brated\s*$", text[clause.start : m.start()], re.I)
        if kind == "rating" and rated:
            start = clause.start + rated.start()
        end = max(m.end(), metric_end) if metric else (m.end() if not (rating_after or dur) else metric_from)
        num_start = m.start("cur") if m.group("cur") else m.start("num")
        num_end = m.end("pct") if m.group("pct") else (m.end("plus") if m.group("plus") else (m.end("scale") if m.group("scale") else m.end("num")))
        claims.append(
            Claim(
                kind=kind,
                start=start,
                end=end,
                text=text[start:end].strip(),
                value=value,
                value_text=m.group(0).strip(),
                num_start=num_start,
                num_end=num_end,
                qualifier=qualifier,
                metric_phrase=metric,
                context=text[clause.start : clause.end],
                unit="seconds" if kind == "duration" else "",
                scope=find_scope(text, m.start(), m.end()),
                claim_date=find_date(text, m.start()),
                extra={"currency": (m.group("cur") or "").strip(), "scale": m.group("scale") or ""},
            )
        )
    for m in VAGUE_RE.finditer(text):
        clause = clause_at(text, m.start(), m.end())
        claims.append(
            Claim(
                kind="count",
                start=m.start(),
                end=m.end(),
                text=m.group(0),
                value=VAGUE_VALUE[m.group("word").lower()],
                value_text=m.group("word"),
                num_start=m.start("word"),
                num_end=m.end() - len(m.group("metric")) - len(" of "),
                qualifier="at_least",
                metric_phrase=m.group("metric"),
                context=text[clause.start : clause.end],
                scope=find_scope(text, m.start(), m.end()),
                claim_date=find_date(text, m.start()),
                extra={"vague": True},
            )
        )
    return claims


def _trim_phrase(text: str, start: int, end: int) -> tuple[int, int]:
    while end > start and text[end - 1] in " ,.;:!?-—–":
        end -= 1
    return start, end


def extract_qualitative(text: str) -> list[Claim]:
    claims = []
    for kind, regex in (("ranking", RANK_RE), ("comparison", COMPARE_RE), ("award", AWARD_RE)):
        for m in regex.finditer(text):
            start, end = _trim_phrase(text, m.start(), m.end())
            phrase = text[start:end]
            if kind == "ranking" and re.fullmatch(r"(?i)(?:the|our)\s+best", phrase.strip()):
                continue
            claims.append(
                Claim(
                    kind=kind,
                    start=start,
                    end=end,
                    text=phrase,
                    context=text[clause_at(text, start, end).start : clause_at(text, start, end).end],
                    scope=find_scope(text, start, end),
                    claim_date=find_date(text, start),
                )
            )
    for m in TESTIMONIAL_RE.finditer(text):
        claims.append(
            Claim(
                kind="testimonial",
                start=m.start(),
                end=m.end(),
                text=m.group(0),
                context=m.group("quote"),
                extra={"quote": m.group("quote"), "who": m.group("who")},
            )
        )
    return claims


def _overlaps(a: Claim, b: Claim) -> bool:
    return a.start < b.end and b.start < a.end


def extract_claims(text: str) -> list[Claim]:
    numbers = extract_numbers(text)
    qualitative = extract_qualitative(text)
    testimonials = [c for c in qualitative if c.kind == "testimonial"]
    out: list[Claim] = list(testimonials)
    # Numbers inside an approved-quote testimonial are part of that testimonial.
    for c in numbers + [q for q in qualitative if q.kind != "testimonial"]:
        if any(_overlaps(c, t) for t in testimonials):
            continue
        if any(_overlaps(c, o) for o in out):
            continue
        out.append(c)
    return sorted(out, key=lambda c: c.start)
