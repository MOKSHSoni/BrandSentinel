"""Compare an extracted claim with the Brand Truth Ledger: metric, scope, date, then value."""

from dataclasses import dataclass, field
from datetime import date, timedelta

from rapidfuzz import fuzz

from ..models import Fact
from .claims import Claim
from .numbers import compare, format_value
from .text import norm_phrase, norm_words

NUMERIC = {"count", "percentage", "money", "rating", "duration"}
QUALITATIVE = {"ranking", "comparison", "award"}


@dataclass
class Verdict:
    outcome: str  # supported | contradicted | unverified | needs_review
    message: str
    explanation: str = ""
    fact: Fact | None = None
    candidates: list[Fact] = field(default_factory=list)
    replacement: str | None = None  # corrected claim text, built only from the cited fact
    relation: dict[int, str] = field(default_factory=dict)  # fact id -> supported | contradicted | compared


def fact_window(f: Fact, by_id: dict[int, Fact], today: date) -> tuple[date, date]:
    end = f.valid_until
    if f.superseded_by_id and f.superseded_by_id in by_id:
        succ_start = by_id[f.superseded_by_id].effective_date - timedelta(days=1)
        end = min(end, succ_start) if end else succ_start
    return f.effective_date, end or today


def metric_match(claim: Claim, f: Fact) -> str | None:
    """'strong' = same metric, 'ambiguous' = could be this metric, 'related' = same noun, different metric."""
    phrase = norm_phrase(claim.metric_phrase)
    context = norm_phrase(claim.context)
    aliases = [norm_phrase(a) for a in [f.metric, *f.aliases] if a]
    if phrase:
        # The metric phrase may run on into a verb ("customers paid"), so try its leading words too.
        words = phrase.split()
        prefixes = [" ".join(words[:k]) for k in range(len(words), 0, -1)]
        if any(p == a for p in prefixes for a in aliases):
            return "strong"
        if any(p == norm_phrase(t) for p in prefixes for t in f.ambiguous_terms):
            return "ambiguous"
    elif claim.kind in ("duration", "rating", "money", "percentage") or not phrase:
        # Units like "seconds" or "stars" carry no metric; look for the metric in the clause instead.
        padded = f" {context} "
        if any(a and f" {a} " in padded for a in aliases):
            return "strong"
        if any(t and f" {norm_phrase(t)} " in padded for t in f.ambiguous_terms):
            return "ambiguous"
    if claim.kind != "count":
        # Percentages, money, ratings and durations often name the metric elsewhere in the clause
        # ("99.2% of UPI payments on Nimbus Pay succeed"): accept when every alias word is in the clause.
        clause_words = set(context.split())
        if any(len(a.split()) > 1 and set(a.split()) <= clause_words for a in aliases):
            return "strong"
        if any(len(norm_phrase(t).split()) >= 1 and set(norm_phrase(t).split()) <= clause_words for t in f.ambiguous_terms if t):
            return "ambiguous"
    head = phrase.split()[-1] if phrase else ""
    alias_heads = {a.split()[-1] for a in aliases if a} | {norm_phrase(t).split()[-1] for t in f.ambiguous_terms if t}
    if head and head in alias_heads:
        return "related"
    return None


def scope_ok(claim_scope: str | None, fact_scope: str, default_scope: str) -> bool:
    return (claim_scope or default_scope).lower() == fact_scope.lower()


def _replace_value(claim: Claim, f: Fact, text: str) -> str | None:
    if claim.num_start is None or f.value_num is None:
        return None
    if claim.extra.get("vague"):
        new_num = format_value(f.value_num, f.kind)
    elif claim.kind == "percentage":
        new_num = f"{format_value(f.value_num, 'percentage')}%"
    elif claim.kind == "money":
        new_num = f"{claim.extra.get('currency') or '₹'}{format_value(f.value_num, 'money')}"
    elif claim.kind == "duration":
        new_num = format_value(f.value_num, "duration")
    else:
        new_num = format_value(f.value_num, f.kind)
    head = text[claim.start : claim.num_start]
    tail = text[claim.num_end : claim.end]
    if claim.qualifier != "exact" and claim.kind != "duration":
        # Drop "over"/"nearly"/"+" so the corrected claim states the approved value exactly.
        for q in ("more than ", "at least ", "upwards of ", "nearly ", "almost ", "about ", "around ",
                  "approximately ", "roughly ", "close to ", "over ", "under ", "less than ", "up to ", "~"):
            if head.lower().startswith(q):
                head = head[len(q):]
                break
    return f"{head}{new_num}{tail}"


def verify_numeric(claim: Claim, facts: list[Fact], text: str, today: date, default_scope: str) -> Verdict:
    by_id = {f.id: f for f in facts}
    kinds = {claim.kind}
    pool = [f for f in facts if f.kind in kinds and f.status != "draft"]
    levels: dict[str, list[Fact]] = {"strong": [], "ambiguous": [], "related": []}
    for f in pool:
        lvl = metric_match(claim, f)
        if lvl:
            levels[lvl].append(f)

    strong = levels["strong"]
    if not strong:
        current_amb = [f for f in levels["ambiguous"] if f.status == "approved"]
        if current_amb:
            return Verdict(
                "needs_review",
                f"“{claim.metric_phrase or claim.text}” could refer to {', '.join(f.metric.lower() for f in current_amb)}.",
                "The metric in the claim is ambiguous, so a reviewer must decide which approved fact applies.",
                candidates=current_amb,
                relation={f.id: "compared" for f in current_amb},
            )
        related = [f for f in levels["related"] if f.status == "approved"]
        if related:
            r = related[0]
            return Verdict(
                "unverified",
                f"No approved fact covers “{claim.metric_phrase}”.",
                f"{r.key} measures {r.metric.lower()}, which is a different metric from “{claim.metric_phrase}”. "
                "Add an approved source for this figure or remove it.",
                candidates=related,
            )
        return Verdict(
            "unverified",
            "No approved fact covers this claim.",
            "Add an approved source to the Brand Truth Ledger or remove the claim. Unverified is not the same as false.",
        )

    in_scope = [f for f in strong if scope_ok(claim.scope, f.scope, default_scope)]
    if not in_scope and claim.scope is None:
        in_scope = strong  # the metric itself implies a scope (e.g. a Google Play rating)
    if not in_scope:
        current = [f for f in strong if f.status == "approved"]
        scopes = ", ".join(sorted({f.scope for f in current})) or "another scope"
        return Verdict(
            "unverified",
            f"No approved fact covers {claim.metric_phrase or claim.kind} in {claim.scope}.",
            f"Approved figures for this metric cover {scopes}, not {claim.scope}.",
            candidates=current,
            relation={f.id: "compared" for f in current},
        )

    if claim.claim_date:
        d = date.fromisoformat(claim.claim_date)
        dated = [f for f in in_scope if f.status in ("approved", "superseded")
                 and fact_window(f, by_id, today)[0] <= d <= fact_window(f, by_id, today)[1]]
        if not dated:
            return Verdict(
                "needs_review",
                f"No approved fact for {claim.metric_phrase or claim.kind} on {d:%d %b %Y}.",
                "The claim refers to a date that no approved fact version covers.",
                candidates=in_scope,
                relation={f.id: "compared" for f in in_scope if f.status == "approved"},
            )
        chosen = dated
    else:
        chosen = [f for f in in_scope if f.status == "approved"]
        if not chosen:
            retracted = [f for f in in_scope if f.status == "retracted"]
            return Verdict(
                "unverified",
                "The fact behind this claim is no longer approved.",
                ("It was retracted: " + retracted[0].change_note) if retracted else "All versions are superseded.",
                candidates=in_scope[:3],
            )
        expired = [f for f in chosen if f.valid_until and f.valid_until < today]
        if expired and len(expired) == len(chosen):
            f = expired[0]
            return Verdict(
                "needs_review",
                f"{f.label} expired on {f.valid_until:%d %b %Y}.",
                "The approved fact is past its validity date; the brand admin must renew or replace it.",
                fact=f,
                candidates=chosen,
                relation={f.id: "compared"},
            )

    values = {f.value_num for f in chosen}
    if len(values) > 1 and not claim.claim_date:
        return Verdict(
            "needs_review",
            "Approved facts conflict for this metric and scope.",
            "; ".join(f"{f.label}: {f.value_text}" for f in chosen),
            candidates=chosen,
            relation={f.id: "compared" for f in chosen},
        )

    f = sorted(chosen, key=lambda x: x.effective_date)[-1]
    historic = f.status != "approved"
    if claim.value is not None and f.value_num is not None and compare(claim.qualifier, claim.value, f.value_num, f.kind):
        when = f" (valid for {date.fromisoformat(claim.claim_date):%b %Y})" if historic else ""
        return Verdict(
            "supported",
            f"Supported by {f.label}{when}: {f.metric} = {f.value_text} ({f.scope}).",
            "Metric, scope, date and value all match the approved fact.",
            fact=f,
            relation={f.id: "supported"},
        )
    return Verdict(
        "contradicted",
        f"{f.label} gives {f.metric.lower()} as {f.value_text} ({f.scope}), not {claim.value_text}.",
        f"Approved value: {f.value_text}, effective {f.effective_date:%d %b %Y}. Source: {f.source} {f.source_version}.",
        fact=f,
        replacement=None if historic else _replace_value(claim, f, text),
        relation={f.id: "contradicted"},
    )


def verify_qualitative(claim: Claim, facts: list[Fact], today: date, default_scope: str) -> Verdict:
    kinds = {"ranking", "comparison", "award"}
    pool = [f for f in facts if f.kind in kinds]
    claim_norm = norm_phrase(claim.text)
    best, best_score = None, 0.0
    for f in pool:
        for a in [f.metric, f.value_text, *f.aliases]:
            if not a:
                continue
            a_norm = norm_phrase(a)
            if not a_norm:
                continue
            # Every word of the approved wording must appear in the claim; near-spellings score by ratio.
            a_words = set(a_norm.split())
            if len(a_words) > 1 and a_words <= set(claim_norm.split()):
                score = 100
            else:
                score = fuzz.ratio(claim_norm, a_norm) if len(a_words) > 1 else 0
            if score > best_score:
                best, best_score = f, score
    if best is not None and best_score >= 90:
        if best.status != "approved":
            return Verdict(
                "unverified",
                f"{best.label} that backed this claim is {best.status}.",
                "Only current approved facts can support a claim.",
                candidates=[best],
            )
        if not scope_ok(claim.scope, best.scope, default_scope) and claim.scope:
            return Verdict(
                "unverified",
                f"{best.label} supports this in {best.scope}, not {claim.scope}.",
                "Rankings and awards only hold for the scope in which they were granted.",
                candidates=[best],
                relation={best.id: "compared"},
            )
        if best.valid_until and best.valid_until < today:
            return Verdict("needs_review", f"{best.label} expired on {best.valid_until:%d %b %Y}.",
                           "Renew the source before using this claim.", fact=best, relation={best.id: "compared"})
        return Verdict(
            "supported",
            f"Supported by {best.label}: {best.statement or best.value_text}.",
            f"Source: {best.source} {best.source_version}.",
            fact=best,
            relation={best.id: "supported"},
        )
    label = {"ranking": "ranking or superlative", "comparison": "comparison", "award": "award or certification"}[claim.kind]
    return Verdict(
        "unverified",
        f"No approved fact supports this {label}.",
        "Superlatives, comparisons and awards need an approved, current source (for example a dated industry "
        "report). Add one to the ledger or remove the claim.",
    )


def verify_testimonial(claim: Claim, facts: list[Fact]) -> Verdict:
    quote = claim.extra.get("quote", claim.text)
    for f in facts:
        if f.kind != "testimonial":
            continue
        if fuzz.ratio(norm_phrase(quote), norm_phrase(f.value_text)) >= 92:
            if f.status != "approved":
                return Verdict("unverified", f"Testimonial {f.label} is {f.status}.",
                               "Consent or approval for this quote has lapsed.", candidates=[f])
            return Verdict("supported", f"Approved testimonial {f.label} ({f.statement}).",
                           "Quote and attribution match an approved testimonial with recorded consent.",
                           fact=f, relation={f.id: "supported"})
    return Verdict(
        "unverified",
        "This testimonial is not on the approved list.",
        "Customer quotes need recorded consent and approval before publication.",
    )


def verify_claim(claim: Claim, facts: list[Fact], text: str, today: date, default_scope: str) -> Verdict:
    if claim.kind in NUMERIC:
        return verify_numeric(claim, facts, text, today, default_scope)
    if claim.kind in QUALITATIVE:
        return verify_qualitative(claim, facts, today, default_scope)
    if claim.kind == "testimonial":
        return verify_testimonial(claim, facts)
    return Verdict(
        "needs_review",
        "A model flagged this as a claim the rule-based checks cannot verify.",
        "A reviewer should confirm whether it needs an approved source.",
    )
