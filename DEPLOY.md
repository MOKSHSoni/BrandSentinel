# Deploying BrandSentinel (free tier)

The live demo runs as three free services:

| Part | Service | What it hosts |
|---|---|---|
| Database | [Neon](https://neon.tech) | PostgreSQL 16 (facts, rules, versions, findings, sign-offs, audit log) |
| API | [Render](https://render.com) | FastAPI backend (`backend/`) |
| Web app | [Vercel](https://vercel.com) | Next.js frontend (`frontend/`) |
| AI judge | [Groq](https://console.groq.com) | OpenAI-compatible LLM used through the Confidentiality Gateway |

Ollama runs only on your laptop, so the hosted API uses Groq instead. The gateway sends only **public**
content to it. Internal and confidential content is kept local, unless the brand admin approves that tier
under *Insights → Confidentiality Gateway*; that content is then masked before it is sent. Restricted
content is never sent. Rule checks, claim verification and blast radius do not need a model at all.

All three providers need you to sign in, so you do the clicks and the code is ready for them. Pushing
the project to a GitHub repository first makes Render and Vercel easiest to set up.

## 1. Database: Neon

1. Create a Neon project (region: Singapore or Mumbai if offered). PostgreSQL 16.
2. Copy the connection string from *Connection details*. It looks like
   `postgresql://user:password@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
   You can paste it exactly as Neon gives it, because the app converts it for the psycopg driver.

Tables are created and the Nimbus Pay demo brand is seeded on the API's first start.

## 2. AI key: Groq

Create an API key at <https://console.groq.com/keys>. The default model is `openai/gpt-oss-20b` (Groq accounts do not all have the Llama models).
If Groq has retired it, choose any current model from their list and set `EXTERNAL_LLM_MODEL` to its name.

## 3. API: Render

1. *New → Blueprint*, select the repository. Render reads [`render.yaml`](render.yaml).
   (Without a blueprint: *New → Web Service*, set root directory `backend`, build command
   `pip install -r requirements.txt`, start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.)
2. Fill in the secret variables:
   - `DATABASE_URL`: the Neon string
   - `EXTERNAL_LLM_API_KEY`: the Groq key
   - `CORS_ORIGINS`: your Vercel URL from step 4. Every `*.vercel.app` preview is already allowed, so you can leave this blank at first.
3. Deploy, then open `https://<service>.onrender.com/api/health`. You should see `"ok": true` and
   `"external_model": {"configured": true, …}`.

Free Render services sleep after 15 minutes without traffic, and the first request then takes about 30 seconds.
The login page says so while it waits. Open the link a minute before judging to wake the service.

## 4. Web app: Vercel

1. *Add New → Project*, import the repository, set **Root Directory** to `frontend`.
2. Environment variable: `NEXT_PUBLIC_API_URL = https://<service>.onrender.com`. Use no trailing slash.
3. Deploy. The Vercel URL is the link you give the judges.

## 5. Before judging

- Sign in as **Rahul (brand admin)**, then *Insights → Reset demo* to restore a clean Nimbus Pay state.
- Approved facts in the demo are valid until **31 Dec 2026**. If judging happens later, set the Render
  variable `REVIEW_DATE=2026-10-27` so the facts are checked against that date and do not show as expired.
- Model reliability numbers on the Insights page come from `backend/eval/results/*.json`. Those runs used
  the local qwen3 model on a laptop. Re-run with `python eval/run_eval.py --modes all` if you change checks,
  then redeploy.

## Environment variables (API)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | local Postgres | Neon/Render/any PostgreSQL URL |
| `JWT_SECRET` | dev value | Signs login tokens. Render generates one |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins (`*.vercel.app` always allowed) |
| `LOCAL_LLM_ENABLED` | `true` | Set `false` on hosts without Ollama |
| `EXTERNAL_LLM_URL` / `_MODEL` / `_API_KEY` | empty | OpenAI-compatible model behind the gateway |
| `REVIEW_DATE` | today | Fixes "today" for fact validity (demo repeatability) |
| `SEED_ON_STARTUP` | `true` | Seed Nimbus Pay when the database is empty |
