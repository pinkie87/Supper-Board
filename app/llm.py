"""KI-Anbindung: Claude (Anthropic-API) oder ein lokales Modell über Ollama.

Beide liefern strukturiertes JSON nach einem JSON-Schema zurück.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from .config import Settings
from .i18n import T

log = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


async def generate_json(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    provider = settings.llm_provider
    if provider == "claude":
        return await _claude(settings, system, prompt, schema)
    if provider == "ollama":
        return await _ollama(settings, system, prompt, schema)
    raise LLMUnavailable(T("Keine KI eingerichtet (LLM_PROVIDER ist 'none').", "No AI configured (LLM_PROVIDER is 'none')."))


async def _claude(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    import anthropic

    if not settings.anthropic_api_key:
        raise LLMUnavailable(T("ANTHROPIC_API_KEY fehlt.", "ANTHROPIC_API_KEY is missing."))
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        async with client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Lehnt das Modell eine Anfrage ab, übernimmt serverseitig ein passendes Ersatzmodell.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = await stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise LLMError(T("Claude: API-Schlüssel ungültig.", "Claude: invalid API key.")) from e
    except anthropic.RateLimitError as e:
        raise LLMError(T("Claude: Ratenlimit erreicht, bitte später erneut versuchen.", "Claude: rate limit reached, please try again later.")) from e
    except anthropic.APIStatusError as e:
        raise LLMError(T(f"Claude: Fehler {e.status_code}: {e.message}", f"Claude: error {e.status_code}: {e.message}")) from e
    except anthropic.APIConnectionError as e:
        raise LLMError(T("Claude: keine Verbindung zur Anthropic-API.", "Claude: cannot reach the Anthropic API.")) from e

    if message.stop_reason == "refusal":
        raise LLMError(T("Claude hat die Anfrage abgelehnt.", "Claude declined the request."))
    if message.stop_reason == "max_tokens":
        raise LLMError(T("Claude: Antwort wurde abgeschnitten (zu lang).", "Claude: the answer was cut off (too long)."))
    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(T("Claude: Antwort war kein gültiges JSON.", "Claude: the answer was not valid JSON.")) from e


async def _ollama(settings: Settings, system: str, prompt: str, schema: dict[str, Any]) -> dict:
    body = {
        "model": settings.ollama_model,
        "stream": False,
        "format": schema,
        "options": {"temperature": 0.7},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt + "\n\nAntworte ausschließlich mit JSON nach dem vorgegebenen Schema."},
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(900.0, connect=10.0)) as client:
            r = await client.post(f"{settings.ollama_url}/api/chat", json=body)
    except httpx.HTTPError as e:
        raise LLMError(T(f"Ollama nicht erreichbar unter {settings.ollama_url}.", f"Cannot reach Ollama at {settings.ollama_url}.")) from e
    if r.status_code != 200:
        raise LLMError(T(f"Ollama: Fehler {r.status_code}: {r.text[:200]}", f"Ollama: error {r.status_code}: {r.text[:200]}"))
    content = r.json().get("message", {}).get("content", "")
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise LLMError(T("Ollama: Antwort war kein gültiges JSON.", "Ollama: the answer was not valid JSON.")) from e
