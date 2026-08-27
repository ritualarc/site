# The Ritual Arc

A FastAPI website for The Ritual Arc, deployed on Vercel. Initial content is adapted from
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

## Deploying to Vercel

```bash
vercel
```

`main.py` at the project root defines the FastAPI `app` instance. Vercel's FastAPI framework preset
auto-detects this entrypoint and routes every request to it — no `vercel.json` is needed. Templates
live in `templates/` and static assets in `static/`, both resolved relative to `main.py` so they work
the same locally and on Vercel.
