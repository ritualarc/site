import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from account_store import (
    AccountStoreError,
    delete_brand_profile,
    ensure_schema,
    get_account_type,
    get_brand_profile,
    save_account_type,
    save_brand_profile,
)
from ai_analysis import AI_ANALYSIS_CONFIGURED, AIAnalysisError, analyze_brand_website, fetch_website_text
from auth import AUTH0_CLIENT_ID, AUTH0_CONFIGURED, AUTH0_DOMAIN, oauth

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
    ("/login", "Login"),
    ("/signup", "Signup"),
]

# About, Contact, and the legal pages now live on the main marketing site rather
# than this app; RITURAL_ARC_ROOT_DOMAIN points there (e.g. "https://theritualarc.wixsite.com/theritualarc/").
RITURAL_ARC_ROOT_DOMAIN = os.environ.get("RITURAL_ARC_ROOT_DOMAIN", "").rstrip("/")

FOOTER_LINKS = [
    (f"{RITURAL_ARC_ROOT_DOMAIN}/about", "About"),
    (f"{RITURAL_ARC_ROOT_DOMAIN}/contact", "Contact"),
]

LEGAL_LINKS = [
    (f"{RITURAL_ARC_ROOT_DOMAIN}/privacy-policy", "Privacy Policy"),
    (f"{RITURAL_ARC_ROOT_DOMAIN}/accessibility-statement", "Accessibility Statement"),
    (f"{RITURAL_ARC_ROOT_DOMAIN}/terms-and-conditions", "Terms & Conditions"),
]

# Where the "Ritual Arc" logo/wordmark links to. Falls back to this app's own
# home page if the root domain isn't configured, rather than a dead link.
ROOT_DOMAIN_LINK = RITURAL_ARC_ROOT_DOMAIN or "/"


def render(request: Request, template_name: str, **context):
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "nav_links": NAV_LINKS,
            "footer_links": FOOTER_LINKS,
            "legal_links": LEGAL_LINKS,
            "root_domain": ROOT_DOMAIN_LINK,
            **context,
        },
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url="/static/favicon.png")


@app.get("/")
def home(request: Request):
    return render(request, "index.html", active="/")


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


DASHBOARD_TABS = {
    "brand-profile",
    "ai-magic",
    "manual-enrol",
    "delete-profile-confirm",
    "product-profiles",
    "intelligence",
    "search",
    "help",
    "inbox",
}

def _is_unsure(value: str) -> bool:
    return (value or "").strip().lower() == "unsure"


BRAND_PROFILE_FIELDS = [
    ("website_url", "URL of website"),
    ("market_positioning", "Overall market positioning"),
    ("brand_proposition", "Brand proposition"),
    ("aesthetic_positioning", "Aesthetic positioning"),
    ("cultural_lifestyle_positioning", "Cultural or lifestyle positioning"),
    ("fashion_trend_longevity", "Relationship to fashion, trend and/or longevity"),
    ("accessibility_exclusivity", "Accessibility or exclusivity"),
    ("differentiation", "Points of differentiation"),
    ("competitive_landscape", "Perceived competitive landscape"),
]


@app.get("/dashboard")
async def dashboard(request: Request, tab: str = "brand-profile", q: str = ""):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/signup")
    if tab not in DASHBOARD_TABS:
        tab = "brand-profile"
    account_type = request.session.get("account_type") or "Account type not set"

    brand_profile = None
    if tab in ("brand-profile", "manual-enrol"):
        email = user.get("email")
        if email:
            try:
                brand_profile = await get_brand_profile(email)
            except AccountStoreError:
                logger.exception("Failed to load brand profile")

    if tab == "brand-profile" and brand_profile is None:
        # Nothing enrolled yet: skip the two-button chooser and go straight to AI Magic.
        tab = "ai-magic"

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "account_type": account_type,
            "tab": tab,
            "query": q,
            "brand_profile": brand_profile,
            "brand_profile_fields": BRAND_PROFILE_FIELDS,
            "root_domain": ROOT_DOMAIN_LINK,
        },
    )


@app.post("/dashboard/brand-profile")
async def save_brand_profile_form(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/signup")

    email = user.get("email")
    form = await request.form()
    profile = {key: str(form.get(key, ""))[:300] for key, _label in BRAND_PROFILE_FIELDS}

    if email:
        try:
            await save_brand_profile(email, profile)
        except AccountStoreError:
            logger.exception("Failed to save brand profile")

    return RedirectResponse(url="/dashboard?tab=brand-profile", status_code=303)


@app.post("/dashboard/brand-profile/ai-analysis")
async def brand_profile_ai_analysis(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/signup")

    form = await request.form()
    url = str(form.get("url", "")).strip()

    account_type = request.session.get("account_type") or "Account type not set"
    context = {
        "user": user,
        "account_type": account_type,
        "tab": "ai-magic",
        "query": "",
        "brand_profile_fields": BRAND_PROFILE_FIELDS,
        "ai_magic_url": url,
        "root_domain": ROOT_DOMAIN_LINK,
    }

    if not url:
        context["ai_error"] = "Please enter a website URL."
        return templates.TemplateResponse(request, "dashboard.html", context)

    if not AI_ANALYSIS_CONFIGURED:
        context["ai_error"] = "AI analysis isn't configured yet."
        return templates.TemplateResponse(request, "dashboard.html", context)

    try:
        page_text = await fetch_website_text(url)
        profile = await analyze_brand_website(url, page_text, BRAND_PROFILE_FIELDS)
    except AIAnalysisError:
        logger.exception("AI brand analysis failed")
        context["ai_error"] = "Could not analyze that website. Please check the URL and try again."
        return templates.TemplateResponse(request, "dashboard.html", context)

    # Land on the manual-entry form with the AI's answers filled in, then auto-submit
    # it (once any "Unsure" fields are retried) so the whole flow completes hands-free.
    context["tab"] = "manual-enrol"
    context["brand_profile"] = profile
    context["unsure_fields"] = [key for key, _label in BRAND_PROFILE_FIELDS if _is_unsure(profile.get(key))]
    context["auto_save"] = True
    return templates.TemplateResponse(request, "dashboard.html", context)


@app.post("/dashboard/brand-profile/ai-analysis/retry")
async def brand_profile_ai_analysis_retry(request: Request):
    """Re-run AI analysis for just the fields the model was previously unsure about.

    Called via fetch() from the manual-enrol page's own script, not a full page
    navigation, so it returns JSON rather than rendering a template.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401)

    form = await request.form()
    url = str(form.get("url", "")).strip()
    requested_keys = set(form.getlist("fields"))
    fields_to_retry = [(key, label) for key, label in BRAND_PROFILE_FIELDS if key in requested_keys]

    if not url or not fields_to_retry or not AI_ANALYSIS_CONFIGURED:
        return JSONResponse({})

    try:
        page_text = await fetch_website_text(url)
        result = await analyze_brand_website(url, page_text, fields_to_retry)
    except AIAnalysisError:
        logger.exception("AI brand analysis retry failed")
        return JSONResponse({})

    return JSONResponse(result)


@app.post("/dashboard/brand-profile/delete")
async def delete_brand_profile_form(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/signup")

    email = user.get("email")
    if email:
        try:
            await delete_brand_profile(email)
        except AccountStoreError:
            logger.exception("Failed to delete brand profile")

    return RedirectResponse(url="/dashboard?tab=brand-profile", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    if not AUTH0_CONFIGURED:
        return RedirectResponse(url="/")
    params = urlencode({"client_id": AUTH0_CLIENT_ID, "returnTo": str(request.base_url)})
    return RedirectResponse(url=f"https://{AUTH0_DOMAIN}/v2/logout?{params}")
