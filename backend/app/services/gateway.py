"""Confidentiality Gateway: decides, per model request, whether text may leave the organisation."""

import re
from dataclasses import dataclass, field

from ..models import TIERS


def tier_rank(tier: str) -> int:
    return TIERS.index(tier) if tier in TIERS else len(TIERS) - 1  # unknown counts as restricted


def max_tier(*tiers: str) -> str:
    return TIERS[max(tier_rank(t) for t in tiers)] if tiers else "public"


@dataclass
class Route:
    location: str  # local | external | blocked
    reason: str
    mask: bool = False


def route_request(tier: str, local_ok: bool, external_ok: bool, external_tiers: list[str]) -> Route:
    """Public: any approved model. Internal/Confidential: local by default, external only when the admin
    approved that tier (with masking). Restricted: local only. Unclear: local or blocked."""
    if tier not in TIERS:
        return Route("local", "Unknown tier: kept local.") if local_ok else Route("blocked", "Unknown tier and no local model.")
    if local_ok:
        return Route("local", f"{tier.title()} content processed by the local model.")
    if tier == "restricted":
        return Route("blocked", "Restricted content may only use a local model, and none is available.")
    if not external_ok:
        return Route("blocked", "No model is available.")
    if tier == "public":
        return Route("external", "Public content may use an approved external model.")
    if tier in external_tiers:
        return Route("external", f"Admin approved external use for {tier} content; sensitive terms are masked.", mask=True)
    return Route("blocked", f"{tier.title()} content stays local by default and no local model is available.")


@dataclass
class Masker:
    terms: list[str]
    mapping: dict[str, str] = field(default_factory=dict)

    def mask(self, text: str) -> str:
        for i, term in enumerate(sorted(set(self.terms), key=len, reverse=True)):
            if not term:
                continue
            token = f"<TERM_{i + 1}>"
            pattern = re.compile(re.escape(term), re.I)
            if pattern.search(text):
                self.mapping[token] = term
                text = pattern.sub(token, text)
        return text

    def unmask(self, text: str) -> str:
        for token, term in self.mapping.items():
            text = text.replace(token, term)
        return text

    @property
    def masked_fields(self) -> list[str]:
        return list(self.mapping.keys())


def leaks(output: str, confidential_terms: list[str]) -> list[str]:
    """Output check: confidential terms a model response would insert into a draft."""
    return [t for t in confidential_terms if t and re.search(re.escape(t), output, re.I)]
