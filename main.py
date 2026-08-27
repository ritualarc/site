from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="The Ritual Arc")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

templates = Jinja2Templates(directory=BASE_DIR / "templates")

NAV_LINKS = [
    ("/manifesto", "The Manifesto"),
    ("/signals", "Signals"),
    ("/advisory", "Advisory"),
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
    # No email backend is wired up yet; the submission is simply acknowledged.
    return render(request, "contact.html", active="/contact", submitted=True, first_name=first_name)


@app.get("/privacy-policy")
def privacy_policy(request: Request):
    return render(request, "legal.html", active="", page_title="Privacy Policy")


@app.get("/accessibility-statement")
def accessibility_statement(request: Request):
    return render(request, "legal.html", active="", page_title="Accessibility Statement")


@app.get("/terms-and-conditions")
def terms_and_conditions(request: Request):
    return render(request, "legal.html", active="", page_title="Terms & Conditions")
