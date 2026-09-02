# Ritual Arc

A FastAPI website for Ritual Arc, deployed on Vercel. Initial content is adapted from
[theritualarc.wixsite.com/theritualarc](https://theritualarc.wixsite.com/theritualarc).

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit http://127.0.0.1:8000

## Footer links (About, Contact, legal pages)

About, Contact, Privacy Policy, Accessibility Statement, and Terms & Conditions are no longer pages in
this app — they live on the main marketing site instead. The footer (`base.html`, built from
`FOOTER_LINKS`/`LEGAL_LINKS` in `main.py`) links out to that site's own pages at those same clean paths
(`/about`, `/contact`, `/privacy-policy`, `/accessibility-statement`, `/terms-and-conditions`).

| Variable | Required | Description |
| --- | --- | --- |
| `RITURAL_ARC_ROOT_DOMAIN` | yes | Base URL of the marketing site, e.g. `https://theritualarc.wixsite.com/theritualarc/` (trailing slash optional — it's stripped before appending a path) |

Without it set, footer links fall back to bare relative paths (e.g. `/about`), which won't resolve to
anything in this app since those routes were removed.

## Signup / Login / Auth0

The two buttons on `/signup` ("Member" and "Brand") each start an Auth0 Universal Login **signup**
flow. `/login` starts an Auth0 Universal Login **login** flow. Both use the same
`/auth/callback` route and land on the same bare `/dashboard` page, showing the account type
top-left and "Logged in as" (name/email) top-right.

Auth0 is set up as a **Regular Web Application** (server-side Authorization Code flow — this app
renders pages server-side, so it needs a confidential client that can hold a client secret, not a
Single Page Application client).

In the Auth0 dashboard, on that application's settings:

- **Allowed Callback URLs**: `http://127.0.0.1:8000/auth/callback` (local) and
  `https://<your-vercel-domain>/auth/callback` (production)
- **Allowed Logout URLs / Web Origins**: your site's root URL, same pattern

Then set these environment variables (locally via `export`, or in Vercel's Environment Variables
settings):

| Variable | Required | Description |
| --- | --- | --- |
| `AUTH0_DOMAIN` | yes | e.g. `your-tenant.us.auth0.com` |
| `AUTH0_CLIENT_ID` | yes | From the Auth0 application settings |
| `AUTH0_CLIENT_SECRET` | yes | From the Auth0 application settings |
| `SESSION_SECRET_KEY` | yes in production | Random secret used to sign the session cookie; without it a hardcoded dev default is used |

Without `AUTH0_DOMAIN`/`AUTH0_CLIENT_ID`/`AUTH0_CLIENT_SECRET` set, `/signup` shows an "isn't
configured yet" message and `/login` shows "Coming soon", instead of erroring out.

### Remembering Member vs. Brand across logins: Neon database

A Login click doesn't ask which account type the person is — that's only chosen once, at signup.
To recognize returning users, the account type is stored in a Postgres `users` table (`account_store.py`)
at signup time, keyed by the user's email, and looked up again at login time.

**The data is not stored in plaintext.** On startup the server derives two 256-bit keys from a single
`ENCRYPTION_SECRET`:

- `AES key = SHA256(secret‖0x01)` — used to encrypt the account type with **AES-256-GCM**, with a
  fresh random 12-byte IV per write (stored alongside the ciphertext).
- `HMAC key = SHA256(secret‖0x02)` — used to compute **HMAC-SHA256(email)**. Only that HMAC is stored,
  never the email itself; a login recomputes the same HMAC from the email Auth0 returns to find the
  matching row. Because it's HMAC (not a plain hash), the email can't be recovered or brute-forced
  from what's in the database without also knowing the secret.

The `users` table (`email_hmac`, `account_type_ciphertext`, `account_type_iv`, timestamps) is created
automatically on startup if it doesn't already exist.

**Setup:**

1. Create a Neon Postgres database — either through the [Vercel Marketplace Neon
   integration](https://vercel.com/marketplace/neon) (which sets the connection env var for you) or
   directly at [neon.tech](https://neon.tech). Use the **pooled** connection string (the one with
   `-pooler` in the hostname) — it's what lets a serverless function open short-lived connections
   without exhausting Postgres' connection limit.
2. Set these environment variables (locally via `export`, or in Vercel's Environment Variables
   settings):

| Variable | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | yes | Neon's pooled Postgres connection string |
| `ENCRYPTION_SECRET` | yes | A hex-encoded 256-bit (32-byte) random value — see below |

Without these set, signup still works and shows the right account type for that session, but nothing
is persisted, so a later Login can't recover it (the dashboard falls back to "Account type not set").

Generate a value for it with:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

This prints a random 256-bit value as 64 hex characters — paste it directly into Vercel's Environment
Variables (never commit it to the repo). Treat it like a password: anyone with it, plus read access to
the database, can decrypt every stored account type. Rotating it will make existing rows
undecryptable, since they were encrypted with the old key.

## AI brand analysis (Vercel AI Gateway)

"Enrol Brand" (`/dashboard?tab=ai-magic`) fetches the submitted website, strips it down to plain text,
and asks an LLM — via [LangChain](https://python.langchain.com/) (`langchain-openai`'s `ChatOpenAI`)
pointed at the [Vercel AI Gateway](https://vercel.com/docs/ai-gateway)'s OpenAI-compatible endpoint
(`ai_analysis.py`) — to infer answers to the same fields as the manual enrolment form. The whole thing
then auto-saves and lands on the finished profile screen with no extra clicks.

| Variable | Required | Description |
| --- | --- | --- |
| `AI_GATEWAY_API_KEY` | yes | An [AI Gateway API key](https://vercel.com/docs/ai-gateway/authentication-and-byok/api-keys) |
| `AI_MODEL` | yes | The primary Gateway model id, e.g. `anthropic/claude-opus-5` or `openai/gpt-5.6-sol` |
| `AI_MODEL_FALLBACK` | no | A second Gateway model id. If a call to `AI_MODEL` fails, LangChain automatically retries the same request against this model before giving up. |

Without `AI_GATEWAY_API_KEY`/`AI_MODEL` set, "Begin Analysis" shows an "isn't configured yet" message
instead of erroring out. A failed fetch, a total failure of both the primary and fallback model, or a
model response that isn't valid JSON all degrade to an on-page error rather than a crash — parsing is
deliberately lenient (missing fields default to an empty string) since not every model will honor the
requested shape exactly, and this list of fields may grow later.

Whichever model actually served each request (primary or fallback) is logged as `AI brand analysis
served by model: <model id>`, read from the API response itself rather than assumed from config.

## Deploying to Vercel

```bash
vercel
```

`main.py` at the project root defines the FastAPI `app` instance. Vercel's FastAPI framework preset
auto-detects this entrypoint and routes every request to it — no `vercel.json` is needed. Templates
live in `templates/` and static assets in `static/`, both resolved relative to `main.py` so they work
the same locally and on Vercel.
