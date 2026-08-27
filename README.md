# The Ritual Arc

A FastAPI website for The Ritual Arc, deployed on Vercel. Initial content is adapted from
[theritualarc.wixsite.com/theritualarc](https://theritualarc.wixsite.com/theritualarc).

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn api.index:app --reload
```

Visit http://127.0.0.1:8000

## Deploying to Vercel

```bash
vercel
```

The app is served as a single Python serverless function (`api/index.py`) with all routes handled by
FastAPI; `vercel.json` rewrites every request to that function.
