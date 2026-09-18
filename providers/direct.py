"""
Lionel Agent - Direct provider clients (OmniRoute bypass).
Used when OmniRoute is unavailable or returns 503 for everything.
"""
import logging
import time
from typing import List, Optional

import requests

import config
from providers.types import Message, Completion, ProviderError

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 60
MAX_NETWORK_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2


def _classify_http_error(resp, provider_name: str, model: str) -> ProviderError:
    """Shared error classifier. Matches omniroute.py's logic."""
    try:
        body = resp.json()
        err = body.get("error", {})
        if isinstance(err, dict):
            msg = err.get("message", str(err))
        else:
            msg = str(err)
    except Exception:
        msg = resp.text[:200] if resp.text else "(no body)"

    if resp.status_code == 404:
        return ProviderError(
            provider=provider_name, model=model, status_code=404,
            message=f"Model not found: {msg[:200]}",
            retryable=False, permanent=True,
        )
    if resp.status_code in (401, 403):
        return ProviderError(
            provider=provider_name, model=model, status_code=resp.status_code,
            message=f"Auth error: {msg[:200]}",
            retryable=False, permanent=True,
        )
    if resp.status_code in (429, 402):
        return ProviderError(
            provider=provider_name, model=model, status_code=resp.status_code,
            message=f"Rate limit / payment: {msg[:200]}",
            retryable=True,
        )
    if resp.status_code == 503:
        return ProviderError(
            provider=provider_name, model=model, status_code=503,
            message=f"Provider unavailable: {msg[:200]}",
            retryable=True,
        )
    if resp.status_code == 400 and "not available" in msg.lower():
        return ProviderError(
            provider=provider_name, model=model, status_code=400,
            message=f"Model not in catalog: {msg[:200]}",
            retryable=False, permanent=True,
        )
    return ProviderError(
        provider=provider_name, model=model, status_code=resp.status_code,
        message=f"HTTP {resp.status_code}: {msg[:200]}",
        retryable=False,
    )


def _post_with_retries(url, headers, payload, provider_name: str, model: str):
    """POST with retries on network errors only. Returns the response."""
    last_exc = None
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            return requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            last_exc = e
            logger.warning(f"{provider_name} network error (attempt {attempt+1}): {e}")
            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
    raise ProviderError(
        provider=provider_name, model=model, status_code=None,
        message=f"Network error: {last_exc}", retryable=True,
    )


# ============================================================
# GROQ
# ============================================================
def call_groq(model: str, messages: List[Message], max_tokens: int = 2000, temperature: float = 0.7) -> Completion:
    """Call Groq directly. model like 'openai/gpt-oss-120b' or 'openai/gpt-oss-20b'."""
    if not config.GROQ_API_KEY:
        raise ProviderError(provider="groq-direct", model=model, status_code=None,
                            message="GROQ_API_KEY not set", retryable=False, permanent=True)

    # gpt-oss models burn tokens on reasoning; give them room
    max_tokens = max(max_tokens, 200)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(url, headers, payload, "groq-direct", model)
    if resp.status_code != 200:
        raise _classify_http_error(resp, "groq-direct", model)

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ProviderError(provider="groq-direct", model=model, status_code=200,
                            message="Empty choices", retryable=False)

    msg = choices[0].get("message", {})
    text = (msg.get("content") or "").strip()
    if not text:
        # gpt-oss models emit answer in 'reasoning' when content is empty
        text = (msg.get("reasoning") or "").strip()

    usage = data.get("usage", {}) or {}
    return Completion(
        text=text,
        model=data.get("model", model),
        provider="groq-direct",
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=usage.get("total_tokens", 0) or 0,
        cached=False,
        raw=data,
    )


# ============================================================
# GEMINI (new AQ. key format - uses x-goog-api-key header)
# ============================================================
def call_gemini(model: str, messages: List[Message], max_tokens: int = 2000, temperature: float = 0.7) -> Completion:
    """Call Gemini directly. model like 'gemini-3.1-flash-lite'."""
    if not config.GEMINI_API_KEY:
        raise ProviderError(provider="gemini-direct", model=model, status_code=None,
                            message="GEMINI_API_KEY not set", retryable=False, permanent=True)

    # Gemini 3.x models have a 'thinking' mode that eats tokens; give room
    max_tokens = max(max_tokens, 200)

    contents = []
    system_instruction = None
    for m in messages:
        if m.role == "system":
            system_instruction = {"parts": [{"text": m.content}]}
        else:
            role = "user" if m.role == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m.content}]})

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": config.GEMINI_API_KEY,
    }

    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    if system_instruction:
        payload["systemInstruction"] = system_instruction

    resp = _post_with_retries(url, headers, payload, "gemini-direct", model)
    if resp.status_code != 200:
        raise _classify_http_error(resp, "gemini-direct", model)

    data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise ProviderError(provider="gemini-direct", model=model, status_code=200,
                            message="No candidates in response", retryable=False)

    parts = candidates[0].get("content", {}).get("parts", [])

    # Skip thought parts (reasoning); collect actual text parts
    text_parts = []
    for p in parts:
        if p.get("thought"):
            continue
        if "text" in p:
            text_parts.append(p["text"])
    text = " ".join(text_parts).strip()

    # Fallback: if all parts were marked as thoughts, use them anyway
    if not text and parts:
        text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()

    usage = data.get("usageMetadata", {}) or {}
    return Completion(
        text=text,
        model=model,
        provider="gemini-direct",
        prompt_tokens=usage.get("promptTokenCount", 0) or 0,
        completion_tokens=usage.get("candidatesTokenCount", 0) or 0,
        total_tokens=usage.get("totalTokenCount", 0) or 0,
        cached=False,
        raw=data,
    )


# ============================================================
# CLOUDFLARE WORKERS AI
# ============================================================
def call_cloudflare(model: str, messages: List[Message], max_tokens: int = 2000, temperature: float = 0.7) -> Completion:
    """Call Cloudflare Workers AI. model like '@cf/meta/llama-3.3-70b-instruct-fp8-fast'."""
    if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
        raise ProviderError(provider="cloudflare-direct", model=model, status_code=None,
                            message="CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set",
                            retryable=False, permanent=True)

    # Strip the "cloudflare-ai/" or "cf/" prefix if present
    cf_model = model
    for prefix in ("cloudflare-ai/", "cf/"):
        if cf_model.startswith(prefix):
            cf_model = cf_model[len(prefix):]

    url = f"https://api.cloudflare.com/client/v4/accounts/{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{cf_model}"
    headers = {
        "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(url, headers, payload, "cloudflare-direct", model)
    if resp.status_code != 200:
        raise _classify_http_error(resp, "cloudflare-direct", model)

    data = resp.json()
    if not data.get("success", False):
        errors = data.get("errors", [])
        raise ProviderError(provider="cloudflare-direct", model=model, status_code=200,
                            message=f"CF API error: {errors}", retryable=False)

    result = data.get("result", {}) or {}
    text = result.get("response", "") or ""
    usage = result.get("usage", {}) or {}
    return Completion(
        text=text,
        model=cf_model,
        provider="cloudflare-direct",
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=(usage.get("prompt_tokens", 0) or 0) + (usage.get("completion_tokens", 0) or 0),
        cached=False,
        raw=data,
    )


# ============================================================
# HUGGINGFACE (OpenAI-compatible via router)
# ============================================================
def call_huggingface(model: str, messages: List[Message], max_tokens: int = 2000, temperature: float = 0.7) -> Completion:
    """Call HuggingFace Inference via router. model like 'meta-llama/Llama-3.3-70B-Instruct'."""
    if not config.HF_TOKEN:
        raise ProviderError(provider="hf-direct", model=model, status_code=None,
                            message="HF_TOKEN not set", retryable=False, permanent=True)

    # Strip "hf/" or "huggingface/" prefix
    hf_model = model
    for prefix in ("hf/", "huggingface/"):
        if hf_model.startswith(prefix):
            hf_model = hf_model[len(prefix):]

    url = "https://router.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.HF_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": hf_model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(url, headers, payload, "hf-direct", model)
    if resp.status_code != 200:
        raise _classify_http_error(resp, "hf-direct", model)

    data = resp.json()
    choices = data.get("choices", [])
    if not choices:
        raise ProviderError(provider="hf-direct", model=model, status_code=200,
                            message="Empty choices", retryable=False)

    text = choices[0].get("message", {}).get("content", "") or ""
    usage = data.get("usage", {}) or {}
    return Completion(
        text=text,
        model=data.get("model", hf_model),
        provider="hf-direct",
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=usage.get("total_tokens", 0) or 0,
        cached=False,
        raw=data,
    )


# ============================================================
# PING HELPER
# ============================================================
def ping(provider: str, model: str) -> Optional[str]:
    """Quick connectivity check. Returns reply text or None."""
    msg = [Message(role="user", content="Say OK")]
    try:
        if provider == "groq":
            return call_groq(model, msg, max_tokens=50, temperature=0.0).text.strip()
        if provider == "gemini":
            return call_gemini(model, msg, max_tokens=50, temperature=0.0).text.strip()
        if provider == "cloudflare":
            return call_cloudflare(model, msg, max_tokens=50, temperature=0.0).text.strip()
        if provider == "huggingface":
            return call_huggingface(model, msg, max_tokens=50, temperature=0.0).text.strip()
    except ProviderError as e:
        logger.debug(f"{provider} ping failed: {e.message}")
        return None
    except Exception as e:
        logger.debug(f"{provider} ping unexpected: {e}")
        return None
    return None