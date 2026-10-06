"""KI-Anbindung: Claude (Anthropic-API), Ollama oder ein OpenAI-kompatibler Server
(z. B. llama.cpp `llama-server`, LM Studio, vLLM – etwa mit Unsloth-GGUF-Modellen).

Alle liefern strukturiertes JSON nach einem JSON-Schema zurück. Bilder (Fotos von
Rezeptseiten) gehen an das jeweils eingestellte Bildmodell.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from .config import Settings
from .i18n import T

log = logging.getLogger(__name__)

# Lokale Modelle können – besonders ohne Grafikkarte – lange brauchen.
LOCAL_TIMEOUT = httpx.Timeout(1800.0, connect=10.0)
PROVIDERS = ("claude", "ollama", "openai")


class LLMError(Exception):
    pass


class LLMUnavailable(LLMError):
    pass


# Ein Bild: (MIME-Typ, Base64-Daten ohne "data:"-Präfix)
Image = tuple[str, str]


async def generate_json(settings: Settings, system: str, prompt: str, schema: dict[str, Any],
                        images: list[Image] | None = None) -> dict:
    provider = settings.llm_provider
    if provider == "claude":
        return await _claude(settings, system, prompt, schema, images or [])
    if provider == "ollama":
        return await _ollama(settings, system, prompt, schema, images or [])
    if provider == "openai":
        return await _openai(settings, system, prompt, schema, images or [])
    raise LLMUnavailable(T("Keine KI eingerichtet (LLM_PROVIDER ist 'none').", "No AI configured (LLM_PROVIDER is 'none')."))


def parse_json(text: str) -> dict:
    """JSON aus einer Modellantwort lesen; lokale Modelle setzen es manchmal in ```-Blöcke
    oder schreiben vorher noch einen Gedankengang (<think>…</think>)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise json.JSONDecodeError("kein Objekt", text, 0)
    return data


async def _claude(settings: Settings, system: str, prompt: str, schema: dict[str, Any], images: list[Image]) -> dict:
    import anthropic

    if not settings.anthropic_api_key:
        raise LLMUnavailable(T("ANTHROPIC_API_KEY fehlt.", "ANTHROPIC_API_KEY is missing."))
    content: list[dict] | str = prompt
    if images:
        content = [{"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}} for mime, data in images]
        content.append({"type": "text", "text": prompt})
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        async with client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=64000,
            system=system,
            messages=[{"role": "user", "content": content}],
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


async def _ollama(settings: Settings, system: str, prompt: str, schema: dict[str, Any], images: list[Image]) -> dict:
    user: dict[str, Any] = {"role": "user", "content": prompt + "\n\nAntworte ausschließlich mit JSON nach dem vorgegebenen Schema."}
    model = settings.ollama_model
    if images:
        user["images"] = [data for _, data in images]
        model = settings.ollama_vision_model or settings.ollama_model
    body = {
        "model": model,
        "stream": False,
        "format": schema,
        # Für das Abschreiben von Fotos möglichst wenig Fantasie
        "options": {"temperature": 0.1 if images else 0.7},
        "messages": [{"role": "system", "content": system}, user],
    }
    try:
        async with httpx.AsyncClient(timeout=LOCAL_TIMEOUT) as client:
            r = await client.post(f"{settings.ollama_url}/api/chat", json=body)
    except httpx.HTTPError as e:
        raise LLMError(T(f"Ollama nicht erreichbar unter {settings.ollama_url}. Läuft der PC mit Ollama?",
                         f"Cannot reach Ollama at {settings.ollama_url}. Is the PC running Ollama switched on?")) from e
    if r.status_code != 200:
        raise LLMError(T(f"Ollama ({model}): Fehler {r.status_code}: {r.text[:200]}", f"Ollama ({model}): error {r.status_code}: {r.text[:200]}"))
    try:
        return parse_json(r.json().get("message", {}).get("content", ""))
    except (json.JSONDecodeError, ValueError) as e:
        raise LLMError(T("Ollama: Antwort war kein gültiges JSON.", "Ollama: the answer was not valid JSON.")) from e


async def _openai(settings: Settings, system: str, prompt: str, schema: dict[str, Any], images: list[Image]) -> dict:
    """OpenAI-kompatible Chat-Schnittstelle, wie sie llama.cpp, LM Studio und vLLM anbieten."""
    model = settings.openai_model
    content: list[dict] | str = prompt + "\n\nAntworte ausschließlich mit JSON nach dem vorgegebenen Schema."
    if images:
        model = settings.openai_vision_model or settings.openai_model
        content = [{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}} for mime, data in images]
        content.append({"type": "text", "text": prompt + "\n\nAntworte ausschließlich mit JSON nach dem vorgegebenen Schema."})
    body: dict[str, Any] = {
        "model": model,
        "stream": False,
        "temperature": 0.1 if images else 0.7,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "result", "schema": schema}},
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"} if settings.openai_api_key else {}
    url = f"{settings.openai_url}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=LOCAL_TIMEOUT, headers=headers) as client:
            r = await client.post(url, json=body)
            if r.status_code == 400 and "response_format" in r.text:
                # Manche Server kennen kein JSON-Schema – dann nur per Anweisung
                body.pop("response_format")
                r = await client.post(url, json=body)
    except httpx.HTTPError as e:
        raise LLMError(T(f"KI-Server nicht erreichbar unter {settings.openai_url}. Läuft der PC?",
                         f"Cannot reach the AI server at {settings.openai_url}. Is the PC switched on?")) from e
    if r.status_code != 200:
        raise LLMError(T(f"KI-Server ({model}): Fehler {r.status_code}: {r.text[:200]}", f"AI server ({model}): error {r.status_code}: {r.text[:200]}"))
    try:
        text = r.json()["choices"][0]["message"]["content"]
        return parse_json(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as e:
        raise LLMError(T("KI-Server: Antwort war kein gültiges JSON.", "AI server: the answer was not valid JSON.")) from e
