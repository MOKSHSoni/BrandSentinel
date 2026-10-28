# BrandSentinel

**Team ChaturYukti** (Akshat Dhoka, Dhruv Mehta, Moksh Soni) · Inkloom AI problem statement: *intelligent brand governance before publication*

BrandSentinel checks marketing content against a versioned store of approved facts and brand rules before it is
published. It shows the evidence behind every finding, and when an approved fact changes it tells you which drafts
need re-review.

The demo brand, **Nimbus Pay** (a UPI payments app), is fictional.

## What works

All of the plan's Core MVP is built and tested end to end. Parts of the Next tier are built too.

| Plan item | Where it lives | Status |
|---|---|---|
| Versioned Brand Truth Ledger: metric, value, scope, effective date, validity, source and version, supersedes | `backend/app/models.py` (`Fact`), Ledger page | Core: done |
| Text, DOCX (and PDF) intake | `services/intake.py` | Core: done |
| Terminology, competitor terms, banned phrases, required disclaimers, tone lexicon | `services/rules.py`, Rulebook page | Core: done |
| Claim extraction: numbers, rankings, comparisons, awards, testimonials, vague quantities | `services/claims.py` | Core: done |
| Claim verification with four outcomes (metric, then scope, then date, then value) | `services/verify.py` | Core: done |
| Evidence receipts that cite the fact or rule behind every finding | `serializers.py`, `FindingCard.tsx` | Core: done |
| Three-way correction check: fact-backed, removes the violation, serves the stated goal | `services/analysis.py` | Core: done |
| Version-bound sign-off: content hash, rulebook version, fact versions; overrides need a reason | `services/governance.py` | Core: done |
| Audit history, comments, roles (creator, agency creator, manager, brand admin) | `AuditLog`, `Comment`, `auth.py` | Core: done |
| Blast radius: a fact superseded or retracted, or a rule changed, flags the affected drafts and sign-offs | `services/governance.py`, Blast radius page | Core: done |
| AI judge (claim extraction backup, tone, goal check), used only where rules end, with schema-validated output | `services/llm.py` | Core: done |
| Confidentiality Gateway: sensitivity tiers, effective tier, routing, masking, output check, call log, role-based evidence | `services/gateway.py`, Insights page | Next tier: done |
| Recurring-issue view (which checks reviewers dismiss or override) | Insights page | Next tier: done |
| Measured reliability: 50 labelled drafts, counts per check and severity, two LLM baselines | `backend/eval/`, Insights page | done |
| Image checks (WCAG contrast, palette, logo), alt text inside DOCX | – | Not built (future work) |
| Web-page intake, Guideline Health Radar, Google Docs/CMS plugin | – | Later tier (future work) |

## How a review runs

1. **Intake.** Text, `.docx` or `.pdf` is turned into one normalised string, and a new version is stored with its SHA-256 hash.
2. **Gateway.** Codenames and personal data (PAN, Aadhaar, GSTIN, phone, e-mail) are detected. The effective tier is the
   highest tier of anything in the request, and it decides whether the model is local, external with masking, or blocked.
3. **Rule checks.** Deterministic checks run, and each one cites its rule and quotes the guideline.
4. **Claim verification.** Each claim is matched to the ledger on metric (exact, ambiguous, or the same noun with a
   different metric), then scope, then date (it picks the fact version that was valid on the claimed date), then value
   (taking qualifiers such as *over*, *nearly* and *under* into account). The outcome is *Supported*, *Contradicted*,
   *Unverified* or *Needs review*.
5. **AI judge.** The model handles only what rules cannot decide: extra claims (shown as low-precision suggestions),
   tone, and the goal check. The draft is passed as data, and the output must match a fixed JSON schema and quote the
   draft exactly, or it is dropped.
6. **Checked fixes.** A fix is shown only if it passes all three checks: (a) every claim it makes is supported by
   an approved fact; (b) re-running the checks finds no remaining or new violation; (c) the model agrees it still
   serves the creator's stated goal. Without a model, (c) is marked for the reviewer to confirm.
7. **Human review.** The creator accepts, edits (the edit is re-checked) or dismisses a fix with a reason. Applying fixes creates a new version, which is reviewed again.
8. **Sign-off.** The manager signs off one exact version. The sign-off is refused while blocking findings are open,
   unless each is overridden with a reason. It is also refused if the rulebook or a cited fact changed since the review.

**Blast radius.** Every reviewed version stores the fact versions it relied on (`citations`). Superseding F-12 v3
looks up that table. It flags the latest version of every affected draft for re-review and marks each sign-off
that relied on F-12 v3 as needing renewal. A fact change that flags 500 stored drafts takes about 0.7 s in the
tests (657 ms on SQLite, 668 ms on PostgreSQL; target under 2 s). The 3-draft demo takes about 9 ms.

## Run locally (Windows, macOS or Linux)

Prerequisites: Python 3.11, Node 20+, PostgreSQL 16, and optionally [Ollama](https://ollama.com) with
`ollama pull qwen3:4b-instruct-2507-q4_K_M`.

```bash
# database (once)
psql -U postgres -c "CREATE DATABASE brandsentinel;"

# API on http://localhost:8000
cd backend
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                   # edit DATABASE_URL if your password differs
uvicorn app.main:app --port 8000

# web app on http://localhost:3000
cd frontend
npm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
npm run dev
```

The first start creates the tables and seeds Nimbus Pay: 4 users, 12 facts (14 versions), 7 rules and 3 stored drafts.
Open <http://localhost:3000>, pick a person and follow the four-step guide on the dashboard.

| Person | Role | Can do |
|---|---|---|
| Priya Shah | Creator (in-house) | Upload drafts; accept, edit or dismiss fixes |
| Arjun Rao | Creator (Bluefin Agency) | The same, but sees fact IDs without internal sources or internal figures |
| Meera Iyer | Manager | Sign off, request changes, reject, override with a reason |
| Rahul Verma | Brand admin | Approve and version facts and rules, approve external-model tiers, reset the demo |

The demo password for every account is `demo1234`. The login page signs you in with one click.

## Tests

```bash
cd backend
python -m pytest -q                                    # SQLite, no model needed
TEST_DATABASE_URL=postgresql+psycopg://postgres:<pw>@localhost:5432/brandsentinel_test python -m pytest -q
```

There are 47 tests. They cover number parsing, every claim type, the four outcomes and the near-misses (metric, scope,
date, expiry, conflicting facts), every rule type, gateway routing and masking, all three correction checks
(including a goal check that fails), rejection of off-schema model output, the full four-step journey over HTTP,
permissions, role-based evidence, override and dismissal reasons, edit-after-sign-off, rulebook changes,
retraction, PDF and DOCX intake, the rule that restricted content never reaches an external model, and blast
radius over 500 drafts in under 2 seconds.

## Measured reliability

`python eval/run_eval.py --modes all` runs the labelled set (`backend/eval/dataset.json`: 10 clean, 18 single-error,
8 realistic multi-issue, 10 near-miss and 4 ambiguous drafts) through BrandSentinel and through two baselines: a
general LLM given the brand guide, and a general LLM given the same structured facts. Results are written to
`backend/eval/results/` and shown on the Insights page.

Measured on 27 Oct 2026. Model runs used `qwen3:4b-instruct-2507` on a laptop through Ollama.

| System | Critical recall (target ≥ 0.95) | Major precision / recall (target ≥ 0.90) | Minor precision | Correct fact cited | False alarms per clean draft |
|---|---|---|---|---|---|
| BrandSentinel, rules only | **15/15** | **31/31 · 31/32** | 6/6 | 34/34 | 0.0 |
| BrandSentinel, rules + local AI judge | **15/15** | **31/32 · 31/32** | 6/8 | 34/34 | 0.0 |
| Baseline: LLM given the brand guide | 10/15 | 12/30 · 12/32 | 0/6 | 0/16 | 0.7 |
| Baseline: LLM given the same structured facts | 6/15 | 16/49 · 16/32 | 1/5 | 8/12 | 1.0 |

The third baseline gives the model the same structured facts that BrandSentinel uses. It shows that most of the
gain comes from the pipeline (matching metric, then scope, then date, then value), not just from having the data.

- Corrections: with the AI judge, 20 of 22 candidate fixes passed all three checks and were shown. The model rejected
  2 in the goal check.
- The one miss in both pipelines is R04, "settlements land in your account the same day", a claim with no number or
  superlative. The AI judge extracts it, but marks it *Needs review* (a low-precision suggestion) instead of *Unverified*.
- The AI judge added 2 minor false alarms. One was a tone comment on "Big news"; the other was on the injected text
  in R06, which the injection check already reports.

The team wrote and labelled the test set, which is small and synthetic. It supports a first demonstration, not
general performance claims. The manual-checklist baseline is timed by people and is not automated here.

## Deviations from the Round 1 plan

- **Vale → Python rule engine.** The rule checks are in Python (`services/rules.py`) and work like Vale. This
  avoids shipping a Go binary to the free host. Rules are editable data, and every change creates a new
  rulebook version.
- **pgvector not used.** With a ledger of tens of facts, alias and fuzzy matching (rapidfuzz) gave predictable,
  explainable matches. Semantic search can be added with pgvector when the ledger grows.
- **Microsoft Presidio → regex detectors and a codename dictionary.** These cover PAN, Aadhaar, GSTIN, phone
  and e-mail. Presidio's spaCy models are too large for the free host.
- **LangGraph not needed.** The workflow is a state machine persisted in PostgreSQL (draft status, version and
  review state), which the plan named as the simpler option.
- **Hosted AI.** Locally the AI judge uses Ollama. The hosted demo uses an OpenAI-compatible API (Groq) through
  the gateway, for public content only by default.

## Limitations

- **Only as good as the ledger.** A missing fact gives *Unverified*, not a verdict.
- **The model can be wrong.** Model findings are marked by source and shown as suggestions, and a person decides.
- **Sign-off is not publishing control.** A publishing integration is future work.
- **Masking cannot hide everything.** Drafts containing codenames are treated as restricted and kept local.
- **Image checks are not built.**
