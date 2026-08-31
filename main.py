import logging
import os
import smtplib
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from auth import AUTH0_CONFIGURED, oauth
from mailer import EmailNotConfiguredError, send_contact_email

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="The Ritual Arc")

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
def login(request: Request):
    return render(request, "coming_soon.html", active="/login", page_title="Login")


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

    request.session["account_type"] = ACCOUNT_TYPES[account_type]
    redirect_uri = request.url_for("auth_callback")
    return await oauth.auth0.authorize_redirect(request, redirect_uri, screen_hint="signup")


@app.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    token = await oauth.auth0.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    request.session["user"] = dict(userinfo)
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard")
def dashboard(request: Request):
    user = request.session.get("user")
    account_type = request.session.get("account_type")
    if not user or not account_type:
        return RedirectResponse(url="/signup")
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "account_type": account_type}
    )


@app.get("/privacy-policy")
def privacy_policy(request: Request):
    return render(request, "legal.html", active="", page_title="Privacy Policy")


@app.get("/accessibility-statement")
def accessibility_statement(request: Request):
    return render(request, "legal.html", active="", page_title="Accessibility Statement")


@app.get("/terms-and-conditions")
def terms_and_conditions(request: Request):
    return render(request, "legal.html", active="", page_title="Terms & Conditions")
