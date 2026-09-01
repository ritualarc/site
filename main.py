import logging
import os
import smtplib
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from account_store import AccountStoreError, ensure_schema, get_account_type, save_account_type
from auth import AUTH0_CLIENT_ID, AUTH0_CONFIGURED, AUTH0_DOMAIN, oauth
from mailer import EmailNotConfiguredError, send_contact_email

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_schema()
    except AccountStoreError:
        logger.exception("Failed to ensure database schema on startup")
    yield


app = FastAPI(title="Ritual Arc", lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "dev-insecure-secret-key-change-me"),
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

NAV_LINKS = [
    ("/manifesto", "The Manifesto"),
    ("/signals", "Signals"),
    ("/advisory", "Advisory"),
    ("/login", "Login"),
    ("/signup", "Signup"),
]


def render(request: Request, template_name: str, **context):
    return templates.TemplateResponse(
        request,
        template_name,
        {"nav_links": NAV_LINKS, **context},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url="/static/favicon.png")


@app.get("/")
def home(request: Request):
    return render(request, "index.html", active="/")


@app.get("/manifesto")
def manifesto(request: Request):
    return render(request, "manifesto.html", active="/manifesto")


@app.get("/signals")
def signals(request: Request):
    return render(request, "signals.html", active="/signals")


@app.get("/advisory")
def advisory(request: Request):
    return render(request, "advisory.html", active="/advisory")


@app.get("/about")
def about(request: Request):
    return render(request, "about.html", active="/about")


@app.get("/contact")
def contact(request: Request):
    return render(request, "contact.html", active="/contact", submitted=False)


@app.post("/contact")
def contact_submit(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...),
):
    try:
        send_contact_email(first_name, last_name, email, message)
    except (EmailNotConfiguredError, smtplib.SMTPException, OSError):
        logger.exception("Failed to send contact form email")
        return render(request, "contact.html", active="/contact", submitted=False, send_failed=True)

    return render(request, "contact.html", active="/contact", submitted=True, first_name=first_name)


@app.get("/login")
async def login(request: Request, retry: bool = False):
    if not AUTH0_CONFIGURED:
        return render(request, "coming_soon.html", active="/login", page_title="Login")

    redirect_uri = request.url_for("auth_callback")
    kwargs = {"prompt": "login"} if retry else {}
    return await oauth.auth0.authorize_redirect(request, redirect_uri, **kwargs)


ACCOUNT_TYPES = {"member": "Member", "brand": "Brand"}


@app.get("/signup")
def signup(request: Request):
    return render(request, "signup.html", active="/signup", auth_not_configured=not AUTH0_CONFIGURED)


@app.get("/signup/{account_type}")
async def signup_start(request: Request, account_type: str):
    if account_type not in ACCOUNT_TYPES:
        raise HTTPException(status_code=404)
    if not AUTH0_CONFIGURED:
        return render(request, "signup.html", active="/signup", auth_not_configured=True)

    request.session["pending_account_type"] = ACCOUNT_TYPES[account_type]
    redirect_uri = request.url_for("auth_callback")
    return await oauth.auth0.authorize_redirect(request, redirect_uri, screen_hint="signup")


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = userinfo.get("email")

    # Signup: this browser just chose Member/Brand, so persist it to the database and use it directly.
    chosen_account_type = request.session.pop("pending_account_type", None)
    if chosen_account_type:
        if email:
            try:
                await save_account_type(email, chosen_account_type)
            except AccountStoreError:
                logger.exception("Failed to persist account type to the database")
        account_type = chosen_account_type
    else:
        # Login: no fresh choice was made, so look it up by (HMAC of) email instead.
        account_type = None
        lookup_failed = False
        if email:
            try:
                account_type = await get_account_type(email)
            except AccountStoreError:
                logger.exception("Failed to look up account type from the database")
                lookup_failed = True

        if account_type is None and not lookup_failed:
            # The database was reachable and simply has no row for this email:
            # this is a genuine "you haven't signed up" case, not an outage.
            request.session["pending_login_user"] = dict(userinfo)
            return RedirectResponse(url="/no-account")

    request.session["user"] = dict(userinfo)
    request.session["account_type"] = account_type
    return RedirectResponse(url="/dashboard")


@app.get("/no-account")
def no_account(request: Request):
    pending_user = request.session.get("pending_login_user")
    if not pending_user:
        return RedirectResponse(url="/login")
    return render(request, "no_account.html", active="", user=pending_user)


DASHBOARD_TABS = {"brand-profile", "product-profiles", "intelligence", "search", "help", "inbox"}


@app.get("/dashboard")
def dashboard(request: Request, tab: str = "brand-profile", q: str = ""):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/signup")
    if tab not in DASHBOARD_TABS:
        tab = "brand-profile"
    account_type = request.session.get("account_type") or "Account type not set"
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "account_type": account_type, "tab": tab, "query": q},
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    if not AUTH0_CONFIGURED:
        return RedirectResponse(url="/")
    params = urlencode({"client_id": AUTH0_CLIENT_ID, "returnTo": str(request.base_url)})
    return RedirectResponse(url=f"https://{AUTH0_DOMAIN}/v2/logout?{params}")


@app.get("/privacy-policy")
def privacy_policy(request: Request):
    return render(request, "legal.html", active="", page_title="Privacy Policy")


@app.get("/accessibility-statement")
def accessibility_statement(request: Request):
    return render(request, "legal.html", active="", page_title="Accessibility Statement")


@app.get("/terms-and-conditions")
def terms_and_conditions(request: Request):
    return render(request, "legal.html", active="", page_title="Terms & Conditions")
