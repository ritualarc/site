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

## Deploying to Vercel

```bash
vercel
```

`main.py` at the project root defines the FastAPI `app` instance. Vercel's FastAPI framework preset
auto-detects this entrypoint and routes every request to it — no `vercel.json` is needed. Templates
live in `templates/` and static assets in `static/`, both resolved relative to `main.py` so they work
the same locally and on Vercel.
