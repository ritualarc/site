import html
import json
import logging
import os
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

AI_GATEWAY_API_KEY = os.environ.get("AI_GATEWAY_API_KEY")
AI_MODEL = os.environ.get("AI_MODEL")
AI_MODEL_FALLBACK = os.environ.get("AI_MODEL_FALLBACK")

AI_ANALYSIS_CONFIGURED = bool(AI_GATEWAY_API_KEY and AI_MODEL)

_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh/v1"


def _build_chat_model():
    """Build the LangChain chat model, with AI_MODEL_FALLBACK wired in as a fallback.

    If the primary model call raises, LangChain automatically retries the same
    request against the fallback model before giving up.
    """
    if not AI_ANALYSIS_CONFIGURED:
        return None

    primary = ChatOpenAI(
        model=AI_MODEL,
        api_key=AI_GATEWAY_API_KEY,
        base_url=_GATEWAY_BASE_URL,
        timeout=90,
    )

    if not AI_MODEL_FALLBACK:
        return primary

    fallback = ChatOpenAI(
        model=AI_MODEL_FALLBACK,
        api_key=AI_GATEWAY_API_KEY,
        base_url=_GATEWAY_BASE_URL,
        timeout=90,
    )
    return primary.with_fallbacks([fallback])


_chat_model = _build_chat_model()


class AIAnalysisError(RuntimeError):
    pass


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def _extract_text(page_html: str, limit: int = 6000) -> str:
    without_scripts = _SCRIPT_STYLE_RE.sub(" ", page_html)
    without_tags = _TAG_RE.sub(" ", without_scripts)
    text = html.unescape(without_tags)
    return _WHITESPACE_RE.sub(" ", text).strip()[:limit]


async def fetch_website_text(url: str) -> str:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = f"https://{url}"
    try:
        async with httpx.AsyncClient(
            timeout=10,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; RitualArcBot/1.0)"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise AIAnalysisError(f"Could not fetch {url}: {exc}") from exc
    return _extract_text(response.text)


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AIAnalysisError("AI analysis did not return a JSON object.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIAnalysisError(f"AI analysis returned invalid JSON: {exc}") from exc


async def _invoke_model(
    url: str,
    page_text: str,
    fields: list[tuple[str, str]],
    instructions: str,
    format_instructions: str,
    system_prompt: str,
    log_label: str,
) -> dict:
    """Shared LLM call: ask about `fields`, parse and return the raw JSON reply.

    Returns the parsed dict as-is (values may be plain strings or, for callers that ask
    for it, nested objects) — callers are responsible for shaping their own field values.
    """
    field_list = "\n".join(f'- "{key}": {label}' for key, label in fields)
    prompt = (
        f"{instructions}\n"
        f"{field_list}\n\n"
        f"{format_instructions}\n\n"
        f"Website URL: {url}\n\n"
        f"Webpage content:\n{page_text}\n\n"
        "Respond with ONLY a single JSON object whose keys are exactly the field names above."
    )

    try:
        response = await _chat_model.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ]
        )
    except Exception as exc:
        raise AIAnalysisError(f"AI analysis request failed: {exc}") from exc

    model_used = (response.response_metadata or {}).get("model_name") or (response.response_metadata or {}).get(
        "model"
    )
    logger.info("%s served by model: %s", log_label, model_used or "unknown")

    raw = response.content or ""
    return _parse_json_object(raw)


async def analyze_brand_website(url: str, page_text: str, fields: list[tuple[str, str]]) -> dict:
    """Infer brand profile answers (positioning, proposition, etc.) from page text.

    Parsing is deliberately lenient (missing keys default to "") since fields may be
    added later and not every model will honor the requested shape exactly.
    """
    if not AI_ANALYSIS_CONFIGURED:
        raise AIAnalysisError("AI_GATEWAY_API_KEY and AI_MODEL must be set to run AI analysis.")

    # website_url is supplied by the caller, not inferred — the model isn't asked for it.
    fields_to_infer = [(key, label) for key, label in fields if key != "website_url"]

    data = await _invoke_model(
        url,
        page_text,
        fields_to_infer,
        instructions=(
            "You are a brand analyst. Based only on the webpage content below, infer concise "
            "answers (each under 300 characters) for these brand profile fields:"
        ),
        format_instructions=(
            "For each field, respond with a plain string answer. If the content doesn't give enough "
            "information for a field, put the word Unsure in the field rather than guessing wildly."
        ),
        system_prompt=(
            "You are a precise brand analyst. Respond with ONLY a single valid JSON object — "
            "no markdown, no commentary."
        ),
        log_label="AI brand analysis",
    )
    profile = {key: str(data.get(key) or "")[:300] for key, _label in fields_to_infer}
    profile["website_url"] = url[:300]
    return profile


def _format_tone_value(raw_value) -> str:
    """Encode a tone-of-voice answer as "Choice — Justification" plain text.

    This keeps every field a flat string end to end (manual entry form, save, DB), so
    nothing else in the app needs to know tone fields are structured; only the
    read-only display parses this format back apart (see main.py's _format_tone_field).
    """
    if isinstance(raw_value, dict):
        choice = str(raw_value.get("choice") or "").strip()
        justification = str(raw_value.get("justification") or "").strip()
    else:
        choice = str(raw_value or "").strip()
        justification = ""

    if not choice or choice.lower() == "unsure":
        return "Unsure"

    value = f"{choice} — {justification}" if justification else choice
    return value[:300]


async def analyze_tone_of_voice(url: str, page_text: str, dimensions: list[tuple[str, str]]) -> dict:
    """Secondary AI query: classify the brand's tone of voice along each spectrum in `dimensions`.

    Each dimension key maps to a "word / word" label (e.g. "Playful / Serious"); the model
    is asked to name whichever word fits best plus a short justification.
    """
    if not AI_ANALYSIS_CONFIGURED:
        raise AIAnalysisError("AI_GATEWAY_API_KEY and AI_MODEL must be set to run AI analysis.")

    data = await _invoke_model(
        url,
        page_text,
        dimensions,
        instructions=(
            "You are a brand voice analyst. Based only on the webpage content below, classify this "
            "brand's tone of voice along each of the following spectrums:"
        ),
        format_instructions=(
            'For each spectrum, respond with an object of the form {"choice": "<the single word from '
            'the pair that fits best, exactly as written>", "justification": "<a short one-sentence '
            'justification, under 300 characters>"}. If the content doesn\'t give enough information to '
            'classify a spectrum, set "choice" to "Unsure" and "justification" to an empty string.'
        ),
        system_prompt=(
            "You are a precise brand voice analyst. Respond with ONLY a single valid JSON object — "
            "no markdown, no commentary."
        ),
        log_label="AI tone-of-voice analysis",
    )
    return {key: _format_tone_value(data.get(key)) for key, _label in dimensions}
