"""Seed the fictional Nimbus Pay brand: users, versioned facts, rules and stored drafts."""

import hashlib
import json
import os
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Base
from .models import AppSetting, Draft, EvalRun, Fact, Rule, Rulebook, User
from .services import governance, review

DEMO_PASSWORD = "demo1234"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$")
    return hash_password(password, bytes.fromhex(salt)) == stored


USERS = [
    ("priya@nimbuspay.example", "Priya Shah", "creator", "Nimbus Pay", False),
    ("arjun@bluefin.example", "Arjun Rao", "creator", "Bluefin Agency", True),
    ("meera@nimbuspay.example", "Meera Iyer", "manager", "Nimbus Pay", False),
    ("rahul@nimbuspay.example", "Rahul Verma", "admin", "Nimbus Pay", False),
]

CUSTOMERS = dict(
    kind="count", metric="Active customers", unit="customers", scope="India",
    aliases=["customers", "active customers", "customer base", "active customer base"],
    ambiguous_terms=["users", "active users", "people", "Indians", "families"],
    source="Approved business report",
)

FACTS = [
    dict(key="F-09", version=1, **CUSTOMERS, value_num=50_000, value_text="50,000",
         statement="Trusted by 50,000 active customers across India", effective_date=date(2026, 1, 1),
         valid_until=date(2026, 6, 30), source_version="v1", source_detail="Finance › H1-2026 board pack, slide 3",
         status="superseded"),
    dict(key="F-12", version=1, **CUSTOMERS, value_num=65_000, value_text="65,000",
         statement="Trusted by 65,000 active customers across India", effective_date=date(2026, 7, 1),
         source_version="v1", source_detail="Finance › July business report v1", status="superseded"),
    dict(key="F-12", version=2, **CUSTOMERS, value_num=72_000, value_text="72,000",
         statement="Trusted by 72,000 active customers across India", effective_date=date(2026, 9, 1),
         source_version="v2", source_detail="Finance › August business report v2", status="superseded"),
    dict(key="F-12", version=3, **CUSTOMERS, value_num=80_000, value_text="80,000",
         statement="Trusted by 80,000 active customers across India", effective_date=date(2026, 10, 1),
         valid_until=date(2026, 12, 31), source_version="v3",
         source_detail="Finance › Q3 business report v3, slide 4 (board-approved 28 Sep 2026)", status="approved"),
    dict(key="F-13", version=1, kind="count", metric="Registered merchants", unit="merchants", scope="India",
         aliases=["merchants", "merchant partners", "registered merchants", "merchant outlets", "stores", "shops"],
         ambiguous_terms=["businesses", "partners"], value_num=12_000, value_text="12,000",
         statement="Accepted at 12,000 registered merchants across India", effective_date=date(2026, 9, 1),
         valid_until=date(2027, 3, 31), source="Merchant operations dashboard export", source_version="2026-09",
         source_detail="Ops › merchant registry export 2026-09-01"),
    dict(key="F-14", version=1, kind="percentage", metric="Payment success rate", unit="%", scope="India",
         aliases=["payment success rate", "success rate", "successful payments", "payments succeed",
                  "transaction success rate", "of payments go through"],
         ambiguous_terms=["uptime", "reliability"], value_num=99.2, value_text="99.2%",
         statement="99.2% of UPI payments succeed", effective_date=date(2026, 10, 1), valid_until=date(2026, 12, 31),
         source="Monthly reliability report", source_version="Sep 2026", source_detail="Engineering › SRE monthly report"),
    dict(key="F-15", version=1, kind="duration", metric="Average UPI payment time", unit="seconds", scope="India",
         aliases=["payment time", "payments complete", "payments go through", "send money", "pay", "transfer",
                  "payment", "payments"],
         ambiguous_terms=[], value_num=1.8, value_text="1.8 seconds", statement="UPI payments complete in 1.8 seconds on average",
         effective_date=date(2026, 10, 1), valid_until=date(2026, 12, 31), source="Monthly reliability report",
         source_version="Sep 2026", source_detail="Engineering › SRE monthly report, p95 2.1 s"),
    dict(key="F-16", version=1, kind="rating", metric="Google Play rating", unit="stars", scope="Google Play",
         aliases=["rated", "rating", "star rating", "stars"], ambiguous_terms=[], value_num=4.6, value_text="4.6",
         statement="Rated 4.6 on Google Play", effective_date=date(2026, 10, 15), valid_until=date(2026, 12, 31),
         source="Google Play console snapshot", source_version="2026-10-15", source_detail="Growth › store listing export"),
    dict(key="F-17", version=1, kind="money", metric="First-payment cashback", unit="INR", scope="India",
         aliases=["cashback", "cash back", "cashback on your first upi payment"], ambiguous_terms=["reward"],
         value_num=100, value_text="₹100", statement="₹100 cashback on your first UPI payment (T&C apply)",
         effective_date=date(2026, 10, 1), valid_until=date(2026, 12, 31), source="Festive offer terms",
         source_version="v1", source_detail="Legal › festive offer T&C v1"),
    dict(key="F-18", version=1, kind="count", metric="Cities served", unit="cities", scope="India",
         aliases=["cities", "towns and cities", "cities and towns"], ambiguous_terms=["locations"],
         value_num=450, value_text="450", statement="Available in 450 cities across India",
         effective_date=date(2026, 9, 1), valid_until=date(2027, 3, 31), source="Network coverage report",
         source_version="v2", source_detail="Ops › coverage report v2"),
    dict(key="F-20", version=1, kind="ranking", metric="Fastest-growing UPI app in India",
         unit="", scope="India", aliases=["fastest-growing UPI app", "fastest-growing payments app"],
         ambiguous_terms=[], value_text="India's fastest-growing UPI app",
         statement="India's fastest-growing UPI app (FinServe Industry Report, Q3 2026)",
         effective_date=date(2026, 10, 1), valid_until=date(2027, 3, 31), source="FinServe Industry Report",
         source_version="Q3 2026", source_detail="Licensed PDF in Brand › Evidence"),
    dict(key="F-21", version=1, kind="testimonial", metric="Customer testimonial", unit="", scope="India",
         aliases=[], ambiguous_terms=[], value_text="Nimbus Pay made splitting bills with my flatmates effortless.",
         statement="Ananya K., Pune — written consent recorded 12 Sep 2026", effective_date=date(2026, 9, 12),
         valid_until=date(2027, 9, 12), source="Customer consent form", source_version="CF-2026-114",
         source_detail="Legal › consent forms"),
    dict(key="F-22", version=1, kind="award", metric="PCI DSS v4.0 certification", unit="", scope="India",
         aliases=["PCI DSS certified", "PCI DSS v4.0 certified", "PCI-DSS certified"], ambiguous_terms=[],
         value_text="PCI DSS v4.0 certified", statement="Certified compliant with PCI DSS v4.0",
         effective_date=date(2026, 6, 30), valid_until=date(2027, 6, 30), source="QSA attestation of compliance",
         source_version="AOC 2026", source_detail="Security › AOC 2026 (restricted)"),
    dict(key="F-23", version=1, kind="count", metric="Monthly UPI transactions", unit="transactions", scope="India",
         aliases=["transactions", "monthly transactions", "transactions every month", "transactions a month",
                  "payments every month", "payments a month"], ambiguous_terms=[], value_num=2_400_000,
         value_text="2.4 million", statement="2.4 million UPI transactions every month",
         effective_date=date(2026, 10, 1), valid_until=date(2026, 12, 31), source="Approved business report",
         source_version="v3", source_detail="Finance › Q3 business report v3, slide 6", sensitivity="internal"),
]

TONE_GUIDELINE = (
    "Nimbus Pay sounds calm, clear and expert. Explain benefits plainly and let facts do the work. Avoid hype, "
    "fear-based urgency (\"hurry\", \"last chance\", \"don't miss out\"), ALL-CAPS words and stacked exclamation marks."
)

RULES = [
    dict(key="R-01", kind="terminology", name="Brand name", severity="major", blocking=True, sensitivity="public",
         guideline="Always write the brand name as “Nimbus Pay”: two words, both capitalised. Never abbreviate it.",
         config={"correct": "Nimbus Pay", "variants": ["Nimbus Payments", "NPay", "N-Pay"]}),
    dict(key="R-02", kind="terminology", name="UPI in capitals", severity="major", blocking=True, sensitivity="public",
         guideline="Write “UPI” in capitals; it is the name of the national payments system.",
         config={"correct": "UPI", "variants": []}),
    dict(key="R-03", kind="competitor", name="Competitor names and terms", severity="major", blocking=True,
         sensitivity="internal",
         guideline="Do not name competitors or use their product terms. Comparative claims need legal approval. "
                   "Our contactless feature is called “Tap & Pay”.",
         config={"terms": ["ZipWallet", "PayZoom", "SnapTap"], "replacements": {"SnapTap": "Tap & Pay"},
                 "message": "“{term}” is a competitor’s name or product term."}),
    dict(key="R-04", kind="banned_phrase", name="Absolute promises", severity="critical", blocking=True,
         sensitivity="public",
         guideline="Financial-services copy must not promise outcomes or absolute safety (ASCI guidelines for "
                   "financial products). Describe security measures instead.",
         config={"terms": ["guaranteed returns", "risk-free", "100% safe", "100% secure", "zero risk",
                           "never fails", "fully secure"],
                 "replacements": {"100% safe": "secure", "100% secure": "secure", "fully secure": "secure"},
                 "message": "“{term}” promises an absolute outcome."}),
    dict(key="R-05", kind="disclaimer", name="Offer disclaimer", severity="major", blocking=True, sensitivity="public",
         guideline="Any offer, cashback or discount must carry “T&C apply” in the same piece.",
         config={"trigger_regex": r"\bcash\s?back\b|\b\d+\s?% off\b|\bdiscount\b|\boffers?\b|\bcoupons?\b",
                 "present_regex": r"T\s?&\s?Cs?\s+apply|terms\s+(?:and|&)\s+conditions\s+apply",
                 "required": "T&C apply"}),
    dict(key="R-06", kind="tone", name="Calm, expert tone", severity="minor", blocking=False, sensitivity="public",
         guideline=TONE_GUIDELINE,
         config={"terms": ["act now", "hurry", "don't miss out", "don’t miss out", "last chance",
                           "before it's too late", "you'll regret", "limited time only", "once in a lifetime",
                           "mind-blowing", "insane", "crazy deal", "unbelievable"]}),
    dict(key="R-07", kind="confidential_term", name="Unreleased codenames", severity="critical", blocking=True,
         sensitivity="restricted",
         guideline="Unreleased product names and codenames must not appear in drafts shared outside the core team.",
         config={"terms": ["Project Falcon", "Falcon Card", "Nimbus Gold"],
                 "message": "“{term}” is an unreleased product codename."}),
]

SEED_DRAFTS = [
    dict(title="Diwali festive email", channel="Email", author="priya@nimbuspay.example",
         goal="Drive first payments during Diwali", sign_off=True,
         content="Subject: Light up Diwali with Nimbus Pay\n\nThis Diwali, join 80,000 customers across India who pay "
                 "with Nimbus Pay. Get ₹100 cashback on your first UPI payment. T&C apply.\n\nPayments complete in "
                 "under 2 seconds, so you spend less time paying and more time celebrating."),
    dict(title="Instagram caption: city launch", channel="Instagram", author="arjun@bluefin.example",
         goal="Announce wider availability", sign_off=False,
         content="Now in 450 cities. Over 80,000 customers trust Nimbus Pay for everyday UPI payments. "
                 "Rated 4.6 on Google Play."),
    dict(title="Merchant onboarding blog intro", channel="Blog", author="priya@nimbuspay.example",
         goal="Get merchants to sign up", sign_off=True,
         content="Join over 12,000 merchants who accept UPI payments with Nimbus Pay. Settlements are simple, and "
                 "our support team is here when you need it."),
]

SAMPLES = {
    "launch_post": dict(
        title="LinkedIn launch post", channel="LinkedIn", goal="Build trust in the new app",
        content="Meet the new Nimbus Pay app.\n\nIndia's #1 payments app, trusted by 50,000 customers. Send money, "
                "split bills and pay at over 12,000 merchants, all with UPI.\n\nDownload Nimbus Pay today."),
    "festive_offer": dict(
        title="Agency festive offer banner copy", channel="Display ad", goal="Get existing users to try cashback",
        content="HURRY!! Last chance to grab ₹100 cashback with Nimbus pay. Unlike ZipWallet, our SnapTap payments "
                "are 100% safe and 2x faster than cash. Coming soon: the Falcon Card for premium members. "
                "Join 1 lakh users today!"),
    "near_miss": dict(
        title="Near-miss claims", channel="Website", goal="Show our growth",
        content="Over 80,000 registered users rely on Nimbus Pay. In June 2026, 50,000 customers paid with us. "
                "Nimbus Pay now serves 80,000 customers in Mumbai. We are India's fastest-growing UPI app and "
                "PCI DSS v4.0 certified."),
}


def seed(db: Session, with_drafts: bool = True) -> None:
    users = {}
    for email, name, role, org, agency in USERS:
        u = User(email=email, name=name, role=role, organisation=org, is_agency=agency,
                 password_hash=hash_password(DEMO_PASSWORD))
        db.add(u)
        users[email] = u
    db.flush()
    admin = users["rahul@nimbuspay.example"]

    rows: dict[tuple[str, int], Fact] = {}
    for spec in FACTS:
        f = Fact(created_by_id=admin.id, **spec)
        db.add(f)
        db.flush()
        rows[(f.key, f.version)] = f
    chain = [("F-09", 1), ("F-12", 1), ("F-12", 2), ("F-12", 3)]
    for older, newer in zip(chain, chain[1:]):
        rows[older].superseded_by_id = rows[newer].id
        rows[newer].supersedes_id = rows[older].id
    rows[("F-12", 1)].change_note = "Replaces F-09 after the switch to monthly active customers."

    for spec in RULES:
        db.add(Rule(**spec))
    db.add(Rulebook(version=1, note="Initial Nimbus Pay rulebook"))
    db.add(AppSetting(key="external_tiers", value={"v": []}))
    db.flush()

    if with_drafts:
        manager = users["meera@nimbuspay.example"]
        for spec in SEED_DRAFTS:
            author = users[spec["author"]]
            d = Draft(title=spec["title"], channel=spec["channel"], goal=spec["goal"], created_by_id=author.id)
            db.add(d)
            db.flush()
            v = review.new_version(db, d, spec["content"], author, "Initial upload")
            review.run_review(db, v, author, use_ai=False)
            if spec["sign_off"]:
                governance.sign_off(db, d, manager, "Facts and wording checked.", {})
        load_eval_results(db)
    db.commit()


RESULTS_DIR = Path(__file__).resolve().parents[1] / "eval" / "results"


def load_eval_results(db: Session) -> None:
    """Results measured with `eval/run_eval.py` (model runs need Ollama, so they are measured offline)."""
    found = set()
    for path in sorted(RESULTS_DIR.glob("*.json")):
        db.add(EvalRun(mode=path.stem, results=json.loads(path.read_text(encoding="utf-8"))))
        found.add(path.stem)
    if "pipeline_rules" not in found:
        from .services import evaluation

        facts, rules = evaluation.seeded_ledger()
        db.add(EvalRun(mode="pipeline_rules", results=evaluation.run("pipeline_rules", facts, rules)))


def reset(db: Session, engine) -> None:
    db.close()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def ensure_seeded(db: Session) -> bool:
    if db.scalar(select(User).limit(1)) is None:
        seed(db)
        return True
    return False
