"""Parse and format the numbers that appear in marketing copy."""

import re

SCALES = {
    "k": 1e3,
    "thousand": 1e3,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "m": 1e6,
    "mn": 1e6,
    "million": 1e6,
    "millions": 1e6,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
}

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20,
    "fifty": 50, "hundred": 100,
}

# Qualifier words that change how a claimed value relates to the approved value.
QUALIFIERS = {
    "over": "at_least",
    "more than": "at_least",
    "at least": "at_least",
    "upwards of": "at_least",
    "nearly": "approx",
    "almost": "approx",
    "about": "approx",
    "around": "approx",
    "approximately": "approx",
    "roughly": "approx",
    "close to": "approx",
    "~": "approx",
    "under": "at_most",
    "less than": "at_most",
    "within": "at_most",
    "up to": "at_most",
    "just": "exact",
}

NUMBER_RE = re.compile(
    r"""
    (?P<qual>\b(?:more\ than|at\ least|upwards\ of|nearly|almost|about|around|approximately|roughly|close\ to|over|under|less\ than|within|up\ to|just)\s+|~\s?)?
    (?P<cur>₹\s?|\brs\.?\s?|\binr\s?|\$\s?)?
    (?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)
    (?:\s?(?P<scale>k|thousand|lakhs?|lac|mn|m|million|crores?|cr|bn|b|billion)\b)?
    (?P<plus>\s?\+)?
    (?P<pct>\s?%|\s?percent\b)?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def to_float(num: str, scale: str | None = None) -> float:
    value = float(num.replace(",", ""))
    if scale:
        value *= SCALES[scale.lower()]
    return value


def format_value(value: float, kind: str = "count") -> str:
    if kind in ("percentage", "rating", "duration"):
        return f"{value:g}"
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.2f}"


def compare(qualifier: str, claimed: float, approved: float, kind: str) -> bool:
    """True when the claimed value is consistent with the approved value."""
    if approved == 0:
        return claimed == 0
    if kind == "duration":
        # Lower is better: "in under 2 seconds" is fine when the approved time is 1.8 s.
        if qualifier in ("at_most", "approx"):
            return approved <= claimed * 1.05
        return abs(claimed - approved) / approved <= 0.01
    if kind == "percentage":
        # Percentage points, not relative error: 99.9% vs an approved 99.2% is a different claim.
        if qualifier == "at_least":
            return claimed <= approved
        if qualifier == "approx":
            return abs(claimed - approved) <= 0.5
        if qualifier == "at_most":
            return claimed >= approved
        return abs(claimed - approved) <= 0.05
    if kind == "rating":
        if qualifier == "at_least":
            return claimed <= approved
        return abs(claimed - approved) <= 0.05
    if qualifier == "at_least":
        return claimed <= approved
    if qualifier == "approx":
        return abs(claimed - approved) / approved <= 0.05
    if qualifier == "at_most":
        return claimed >= approved * 0.95
    return abs(claimed - approved) / approved <= 0.01
