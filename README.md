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

## Contact form email

The `/contact` form sends an email via SMTP (`mailer.py`) rather than storing submissions. It needs
these environment variables set (locally via `export`, or in the Vercel project's Environment
Variables settings):

| Variable | Required | Description |
| --- | --- | --- |
| `SMTP_USERNAME` | yes | The sending account's address, e.g. `theritualarc@gmail.com` |
| `SMTP_PASSWORD` | yes | An app password for that account (for Gmail: enable 2-Step Verification, then create one at myaccount.google.com/apppasswords) |
| `SMTP_HOST` | no | Defaults to `smtp.gmail.com` |
| `SMTP_PORT` | no | Defaults to `465` |
| `CONTACT_RECIPIENT` | no | Defaults to `theritualarc@gmail.com` |

Without `SMTP_USERNAME`/`SMTP_PASSWORD` set, submissions fail gracefully with an on-page error message
instead of pretending to succeed.

## Signup / Auth0

The two buttons on `/signup` ("Customer" and "Company") each start an Auth0 Universal Login signup
flow (`auth.py` + the `/signup/{account_type}` and `/auth/callback` routes in `main.py`), then land on
a bare `/dashboard` page showing the chosen account type top-left and "Logged in as" (name/email)
top-right.

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
configured yet" message instead of the buttons erroring out.

## Deploying to Vercel

```bash
vercel
```

`main.py` at the project root defines the FastAPI `app` instance. Vercel's FastAPI framework preset
auto-detects this entrypoint and routes every request to it — no `vercel.json` is needed. Templates
live in `templates/` and static assets in `static/`, both resolved relative to `main.py` so they work
the same locally and on Vercel.
