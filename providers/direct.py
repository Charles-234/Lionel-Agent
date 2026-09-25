"""
Lionel Agent - Direct provider clients (OmniRoute bypass).

Security rules:
- Never expose provider internals or hidden reasoning to users.
- Provider/API error details are logged server-side only.
- Public ProviderError messages are sanitized.
- Credentials are never logged.
"""

import base64
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


# ============================================================
# ERROR HANDLING
# ============================================================

def _extract_provider_error(resp) -> str:
    """
    Extract a short provider error message for SERVER-SIDE logging.

    This value must never be used directly as a user-facing error.
    """
    try:
        body = resp.json()
        err = body.get("error", {})

        if isinstance(err, dict):
            message = err.get("message", str(err))
        else:
            message = str(err)

        return str(message)[:200]

    except Exception:
        return (resp.text[:200] if resp.text else "(no body)")


def _classify_http_error(
    resp,
    provider_name: str,
    model: str,
) -> ProviderError:
    """
    Convert an HTTP provider failure into a sanitized ProviderError.

    Provider-specific response bodies are retained only in server logs.
    They are never exposed through ProviderError.message.
    """
    detail = _extract_provider_error(resp)

    logger.error(
        "%s HTTP error: model=%s status=%s detail=%s",
        provider_name,
        model,
        resp.status_code,
        detail,
    )

    if resp.status_code == 404:
        return ProviderError(
            provider=provider_name,
            model=model,
            status_code=404,
            message="Requested model is unavailable.",
            retryable=False,
            permanent=True,
        )

    if resp.status_code in (401, 403):
        return ProviderError(
            provider=provider_name,
            model=model,
            status_code=resp.status_code,
            message="Provider authentication or authorization failed.",
            retryable=False,
            permanent=True,
        )

    if resp.status_code in (429, 402, 503):
        return ProviderError(
            provider=provider_name,
            model=model,
            status_code=resp.status_code,
            message="Provider is temporarily unavailable.",
            retryable=True,
        )

    if resp.status_code == 400 and "not available" in detail.lower():
        return ProviderError(
            provider=provider_name,
            model=model,
            status_code=400,
            message="Requested model is unavailable.",
            retryable=False,
            permanent=True,
        )

    return ProviderError(
        provider=provider_name,
        model=model,
        status_code=resp.status_code,
        message="Provider returned an unexpected HTTP error.",
        retryable=False,
    )


def _post_with_retries(
    url,
    headers,
    payload,
    provider_name: str,
    model: str,
):
    """
    POST with retries on network errors only.

    Request payloads and authorization headers are deliberately never
    logged.
    """
    last_exc = None

    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            return requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

        except requests.exceptions.RequestException as exc:
            last_exc = exc

            logger.warning(
                "%s network error: model=%s attempt=%s/%s error=%s",
                provider_name,
                model,
                attempt + 1,
                MAX_NETWORK_RETRIES + 1,
                exc,
            )

            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    logger.error(
        "%s network request exhausted retries: model=%s error=%s",
        provider_name,
        model,
        last_exc,
    )

    raise ProviderError(
        provider=provider_name,
        model=model,
        status_code=None,
        message="Provider network request failed.",
        retryable=True,
    )


def call_openai_compatible(
    model: str,
    messages: List[Message],
    base_url: str,
    api_key: str = "",
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """Call a local OpenAI-compatible server such as Ollama or vLLM."""
    if not base_url:
        raise ProviderError("local", model, None, "Local model endpoint is not configured.", permanent=True)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": message.role, "content": message.content} for message in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    response = _post_with_retries(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        headers,
        payload,
        "local",
        model,
    )
    if response.status_code != 200:
        raise _classify_http_error(response, "local", model)
    data = response.json()
    choices = data.get("choices", [])
    text = ((choices[0].get("message", {}).get("content", "")) if choices else "").strip()
    if not text:
        raise ProviderError("local", model, 200, "Local provider returned an empty response.")
    usage = data.get("usage", {}) or {}
    return Completion(
        text=text,
        model=data.get("model", model),
        provider="local",
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=usage.get("total_tokens", 0) or 0,
        raw=data,
    )


# ============================================================
# GROQ
# ============================================================

def call_groq(
    model: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Call Groq directly.

    Example model:
        openai/gpt-oss-120b
    """
    if not config.GROQ_API_KEY:
        raise ProviderError(
            provider="groq-direct",
            model=model,
            status_code=None,
            message="Groq provider is not configured.",
            retryable=False,
            permanent=True,
        )

    # gpt-oss models may use additional internal reasoning tokens.
    max_tokens = max(max_tokens, 200)

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(
        url,
        headers,
        payload,
        "groq-direct",
        model,
    )

    if resp.status_code != 200:
        raise _classify_http_error(
            resp,
            "groq-direct",
            model,
        )

    data = resp.json()

    choices = data.get("choices", [])

    if not choices:
        raise ProviderError(
            provider="groq-direct",
            model=model,
            status_code=200,
            message="Provider returned no response choices.",
            retryable=False,
        )

    message = choices[0].get("message", {})

    # IMPORTANT:
    # Only normal assistant content is allowed to become Lionel's answer.
    #
    # DO NOT fall back to:
    #     message["reasoning"]
    #
    # Hidden/internal reasoning must never be exposed to users.
    text = (message.get("content") or "").strip()

    if not text:
        raise ProviderError(
            provider="groq-direct",
            model=model,
            status_code=200,
            message="Provider returned an empty response.",
            retryable=False,
        )

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
# GEMINI
# ============================================================

def call_gemini(
    model: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Call Gemini directly.

    Example model:
        gemini-3.1-flash-lite
    """
    if not config.GEMINI_API_KEY:
        raise ProviderError(
            provider="gemini-direct",
            model=model,
            status_code=None,
            message="Gemini provider is not configured.",
            retryable=False,
            permanent=True,
        )

    max_tokens = max(max_tokens, 200)

    contents = []
    system_instruction = None

    for message in messages:
        if message.role == "system":
            system_instruction = {
                "parts": [
                    {
                        "text": message.content,
                    }
                ]
            }

        else:
            role = "user" if message.role == "user" else "model"
            parts = [{"text": message.content}]
            if getattr(message, "image_data", None):
                b64 = base64.b64encode(message.image_data).decode("utf-8")
                mime = getattr(message, "image_mime_type", "image/jpeg") or "image/jpeg"
                parts.append({
                    "inlineData": {
                        "mimeType": mime,
                        "data": b64,
                    }
                })

            contents.append(
                {
                    "role": role,
                    "parts": parts,
                }
            )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

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

    resp = _post_with_retries(
        url,
        headers,
        payload,
        "gemini-direct",
        model,
    )

    if resp.status_code != 200:
        raise _classify_http_error(
            resp,
            "gemini-direct",
            model,
        )

    data = resp.json()

    candidates = data.get("candidates", [])

    if not candidates:
        raise ProviderError(
            provider="gemini-direct",
            model=model,
            status_code=200,
            message="Provider returned no response candidates.",
            retryable=False,
        )

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    # Collect only normal text parts.
    # Gemini thought parts are deliberately excluded.
    text_parts = []

    for part in parts:
        if part.get("thought"):
            continue

        if "text" in part:
            text_parts.append(part["text"])

    text = " ".join(text_parts).strip()

    # IMPORTANT:
    # Do NOT fall back to thought/reasoning parts.
    if not text:
        raise ProviderError(
            provider="gemini-direct",
            model=model,
            status_code=200,
            message="Provider returned an empty response.",
            retryable=False,
        )

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

def call_cloudflare(
    model: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Call Cloudflare Workers AI.

    Example model:
        @cf/meta/llama-3.3-70b-instruct-fp8-fast
    """
    if not config.CLOUDFLARE_API_TOKEN or not config.CLOUDFLARE_ACCOUNT_ID:
        raise ProviderError(
            provider="cloudflare-direct",
            model=model,
            status_code=None,
            message="Cloudflare provider is not configured.",
            retryable=False,
            permanent=True,
        )

    cf_model = model

    for prefix in ("cloudflare-ai/", "cf/"):
        if cf_model.startswith(prefix):
            cf_model = cf_model[len(prefix):]

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{cf_model}"
    )

    headers = {
        "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messages": [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(
        url,
        headers,
        payload,
        "cloudflare-direct",
        model,
    )

    if resp.status_code != 200:
        raise _classify_http_error(
            resp,
            "cloudflare-direct",
            model,
        )

    data = resp.json()

    if not data.get("success", False):
        logger.error(
            "Cloudflare API reported failure: model=%s errors=%s",
            model,
            data.get("errors", []),
        )

        raise ProviderError(
            provider="cloudflare-direct",
            model=model,
            status_code=200,
            message="Cloudflare provider returned an error.",
            retryable=False,
        )

    result = data.get("result", {}) or {}

    text = (result.get("response") or "").strip()

    if not text:
        raise ProviderError(
            provider="cloudflare-direct",
            model=model,
            status_code=200,
            message="Provider returned an empty response.",
            retryable=False,
        )

    usage = result.get("usage", {}) or {}

    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0

    return Completion(
        text=text,
        model=cf_model,
        provider="cloudflare-direct",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cached=False,
        raw=data,
    )


# ============================================================
# HUGGINGFACE
# ============================================================

def call_huggingface(
    model: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Call HuggingFace Inference via router.

    Example model:
        meta-llama/Llama-3.3-70B-Instruct
    """
    if not config.HF_TOKEN:
        raise ProviderError(
            provider="hf-direct",
            model=model,
            status_code=None,
            message="HuggingFace provider is not configured.",
            retryable=False,
            permanent=True,
        )

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
        "messages": [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    resp = _post_with_retries(
        url,
        headers,
        payload,
        "hf-direct",
        model,
    )

    if resp.status_code != 200:
        raise _classify_http_error(
            resp,
            "hf-direct",
            model,
        )

    data = resp.json()

    choices = data.get("choices", [])

    if not choices:
        raise ProviderError(
            provider="hf-direct",
            model=model,
            status_code=200,
            message="Provider returned no response choices.",
            retryable=False,
        )

    text = (
        choices[0]
        .get("message", {})
        .get("content", "")
        or ""
    ).strip()

    if not text:
        raise ProviderError(
            provider="hf-direct",
            model=model,
            status_code=200,
            message="Provider returned an empty response.",
            retryable=False,
        )

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
    """
    Quick connectivity check.

    Returns the provider's normal response text or None.
    Provider errors remain server-side.
    """
    messages = [
        Message(
            role="user",
            content="Say OK",
        )
    ]

    try:
        if provider == "groq":
            return call_groq(
                model,
                messages,
                max_tokens=50,
                temperature=0.0,
            ).text.strip()

        if provider == "gemini":
            return call_gemini(
                model,
                messages,
                max_tokens=50,
                temperature=0.0,
            ).text.strip()

        if provider == "cloudflare":
            return call_cloudflare(
                model,
                messages,
                max_tokens=50,
                temperature=0.0,
            ).text.strip()

        if provider == "huggingface":
            return call_huggingface(
                model,
                messages,
                max_tokens=50,
                temperature=0.0,
            ).text.strip()

    except ProviderError as exc:
        logger.debug(
            "%s ping failed: model=%s status=%s retryable=%s permanent=%s",
            provider,
            model,
            exc.status_code,
            exc.retryable,
            exc.permanent,
        )
        return None

    except Exception:
        logger.exception(
            "%s ping encountered an unexpected error: model=%s",
            provider,
            model,
        )
        return None

    return None