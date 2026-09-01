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

### Remembering Member vs. Brand across logins

A Login click doesn't ask which account type the person is — that's only chosen once, at signup.
To recognize returning users, the account type is written into the user's Auth0 `app_metadata` at
signup time, then read back out of a custom ID token claim at login time. This needs two more
pieces of one-time setup in the Auth0 dashboard:

**1. A Machine-to-Machine application** (Applications → Create Application → Machine to Machine),
authorized for the **Auth0 Management API** with the `update:users` scope. Set its credentials:

| Variable | Required | Description |
| --- | --- | --- |
| `AUTH0_M2M_CLIENT_ID` | yes, to persist account type | From the M2M application settings |
| `AUTH0_M2M_CLIENT_SECRET` | yes, to persist account type | From the M2M application settings |

Without these, signup still works and shows the right account type for that session, but a later
Login won't be able to recover it (the dashboard falls back to "Account type not set").

**2. An Auth0 Action** (Actions → Library → Build Custom → add to the **Login** flow) that copies
`app_metadata.account_type` onto the ID token as a custom claim:

```js
exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://ritualarc.app/account_type";
  if (event.user.app_metadata && event.user.app_metadata.account_type) {
    api.idToken.setCustomClaim(namespace, event.user.app_metadata.account_type);
  }
};
```

The namespace string must match `ACCOUNT_TYPE_CLAIM` in `auth.py` exactly — it's just an
identifier, not a URL that needs to resolve.

## Deploying to Vercel

```bash
vercel
```

`main.py` at the project root defines the FastAPI `app` instance. Vercel's FastAPI framework preset
auto-detects this entrypoint and routes every request to it — no `vercel.json` is needed. Templates
live in `templates/` and static assets in `static/`, both resolved relative to `main.py` so they work
the same locally and on Vercel.
