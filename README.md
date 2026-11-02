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
| Text, DOCX and PDF intake, including pictures in Word files and scanned PDFs | `services/intake.py` | Core: done |
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
| **Round 3 · Brand Impact Simulator:** preview what a fact change, retraction or rule change would do (every affected claim re-verified, before/after), then confirm | `services/simulate.py`, Ledger and Rulebook pages | Done |
| **Round 3 · Evidence Chain:** each finding traced from the sentence to its resolution, stale-evidence marking, copyable receipt | `services/evidence.py`, `EvidenceChain.tsx` | Done |
| **Round 3 · Governance Drift Radar:** recurring findings and reviewer disagreement per period (with denominators and reasons), open risk, fact freshness, linked actions | `services/radar.py`, Drift Radar page | Done |
| Image checks: OCR so claims inside images are verified, WCAG contrast measured on detected text pixels, brand palette | `services/images.py` | Done (logo aspect ratio not built) |
| Alt-text checks for pictures in Word files and images on web pages | `services/intake.py`, `services/webpage.py` | Done (PDFs have no alt-text check) |
| Web-page intake with a safe fetch (public addresses only, size and time limits) | `services/webpage.py` | Done |
| Sensitivity editing for facts and rules (no new version, no rulebook bump) | Ledger and Rulebook pages | Done |
| Specialist reviewer role, Google Docs/CMS plugin | – | Future work |

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

You need Python 3.11, Node 20 or newer and PostgreSQL 16. [Ollama](https://ollama.com) is optional; without a model
every review still runs its rule checks and claim verification, and the AI judge is reported as skipped. To use it:
`ollama pull qwen3:4b-instruct-2507-q4_K_M`.

**1. Get the code and create the database**

```bash
git clone https://github.com/MOKSHSoni/BrandSentinel.git
cd BrandSentinel
psql -U postgres -c "CREATE DATABASE brandsentinel;"
```

**2. Start the API** (first terminal, leave it running)

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then set your PostgreSQL password in DATABASE_URL
uvicorn app.main:app --port 8000
```

Check it at <http://localhost:8000/api/health>. It should answer `"ok": true`.

**3. Start the website** (second terminal, leave it running)

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

**4. Open <http://localhost:3000>,** pick a person and follow the four-step guide on the dashboard.

The first start creates the tables and seeds Nimbus Pay: 4 users, 12 facts (15 versions), 9 rules and 5 stored drafts.
Each creator starts with a draft that has open findings (Priya: "Website hero banner"; Arjun: "Instagram story: Diwali
offer"). One fact change has already happened (F-13 merchants 10,000 → 12,000), so the merchant blog starts flagged by
blast radius and its sign-off needs renewal. The four-step demo then makes a second change of its own (F-12). To start
again at any time, sign in as Rahul and use **Insights → Reset demo**.

Sample files for trying uploads are on the **New draft** page: a Word launch post, a banner image and a Word post with
that banner embedded.

### Troubleshooting

| Problem | Fix |
|---|---|
| `pip` fails with `No such file or directory` on Windows | The folder path is too long for Windows. Clone into a short path such as `C:\dev\BrandSentinel`, or enable long paths. |
| `password authentication failed` when the API starts | Set your PostgreSQL password in `DATABASE_URL` in `backend/.env`. |
| `database "brandsentinel" does not exist` | Run the `CREATE DATABASE` command from step 1. |
| `psql` is not recognised | Use its full path, on Windows `"C:\Program Files\PostgreSQL\16\bin\psql.exe"`. |
| The website says it cannot reach the server | Check the API is running and `NEXT_PUBLIC_API_URL` in `frontend/.env.local` matches it. |
| `libGL.so.1` error on a Linux server | Install the headless OpenCV build, as `render.yaml` does. |
| Reviews take about a minute | That is the local model. Set `LOCAL_LLM_ENABLED=false` in `backend/.env` for rules only. |
| Drafts stay valid only until 31 Dec 2026 | The demo facts end then. Set `REVIEW_DATE=2026-10-27` in `backend/.env` to keep them current. |

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
python -m pytest -q        # 115 tests on SQLite, no model or database setup needed

# the same tests on PostgreSQL (create a database called brandsentinel_test first)
TEST_DATABASE_URL=postgresql+psycopg://postgres:<password>@localhost:5432/brandsentinel_test python -m pytest -q
```

They cover number parsing, every claim type, the four outcomes and the near-misses (metric, scope, date, expiry,
conflicting facts), every rule type, gateway routing and masking, all three correction checks, rejection of off-schema
model output, the full four-step journey over HTTP, permissions, role-based evidence, override and dismissal reasons,
edit-after-sign-off, rulebook changes, retraction and every intake format.

For Round 3 they also prove that the simulator writes nothing and reports the right outcome changes, including a stale
preview being detected at commit; evidence attribution and role filtering; radar counts and time windows with no
invented metrics; OCR claims, contrast, palette and alt text; and the safe web fetch refusing private addresses.

The hardening tests cover what a careless or hostile user does: oversized images and zip bombs, reviews interrupted by a
restart, retrying a running review, repeating a sign-off, acting on a rejected draft, invalid rules and facts, and
editing away text read from an image.

**Browser test.** `e2e/run_e2e.py` drives a real browser through the main journeys, bad input, refreshes, double-clicks,
wrong addresses, role limits, expired sessions and phone width. With the API and website running:

```bash
pip install -r e2e/requirements.txt
playwright install chromium
python e2e/run_e2e.py      # resets the demo data; refuses non-localhost addresses unless you pass --live
```

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

## Round 3 notes

- **OCR:** RapidOCR (ONNX, pure pip install) instead of Tesseract, which the free host cannot install. It loads on the
  first image only (about 100 MB) and the review degrades to a clear "image text could not be read" notice if it is
  unavailable. OCR can drop spaces in large type, so a brand name that differs only in spacing is sent to a person
  instead of being reported as a violation. Problems in text read from an image get no automatic fix: the image itself
  has to be corrected.
- **Contrast** is measured on the detected text pixels: inside each OCR box the pixels are split into text and
  background by brightness (Otsu) and the WCAG ratio is taken between the two average colours.
- **Simulation is read-only:** the proposal is built as in-memory objects that are never saved, and the session is
  rolled back afterwards. Confirming recalculates the impact and says if it changed since the preview.
- **Database:** two new nullable columns (`draft_versions.assets`, `findings.meta`) are added at start-up by an
  additive migration, so an existing database keeps its data.

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
- **Image checks cover measurable properties only.** Logo correctness and design quality still need a person.
- **Image limits.** Images above 25 megapixels are refused, because decoding them would exhaust the free server's memory.
  Up to 8 images are checked per file or web page.
- **Small text in images.** OCR reads a copy scaled to 800 pixels on the long side to stay within the free server's memory, so very small text can be missed.
- **One shared demo.** All visitors use the same data, so testers see each other's changes. Reset demo restores it.
- **The free server sleeps** after about 15 minutes idle; the next visit takes 30–50 seconds.
