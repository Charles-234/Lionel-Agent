"""
Lionel Agent - OmniRoute HTTP client.
Single client that talks to OmniRoute's OpenAI-compatible API.
"""
import json
import time
import logging
from typing import Optional, List

import requests

import config
from providers.types import Message, Completion, ProviderError

logger = logging.getLogger(__name__)

# How long to wait for OmniRoute to respond
REQUEST_TIMEOUT = 60

# Retry on transient network errors only (not on HTTP errors)
MAX_NETWORK_RETRIES = 2
RETRY_BACKOFF_SECONDS = 2


def call(
    model: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Call OmniRoute with the given model and messages.

    Returns a Completion on success.
    Raises ProviderError on failure.

    Provider-specific error details are logged server-side and are
    never included in the public ProviderError message.
    """
    url = f"{config.OMNIROUTE_URL}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.OMNIROUTE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    last_exception = None
    for attempt in range(MAX_NETWORK_RETRIES + 1):
        try:
            resp = requests.post(
                url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            last_exception = e
            logger.warning(
                "OmniRoute network error "
                "(attempt %s/%s): %s",
                attempt + 1,
                MAX_NETWORK_RETRIES + 1,
                e,
            )

            if attempt < MAX_NETWORK_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                continue

            # Exhausted retries.
            raise ProviderError(
                provider="omniroute",
                model=model,
                status_code=None,
                message="OmniRoute network request failed.",
                retryable=True,
            )

        # Got an HTTP response - handle status codes
        if resp.status_code == 200:
            return _parse_success(resp.json(), model)

        # Extract provider details for server-side diagnostics only.
        error_msg = _extract_error_message(resp)

        logger.warning(
            "OmniRoute HTTP error: model=%s status=%s detail=%s",
            model,
            resp.status_code,
            error_msg,
        )

        if resp.status_code == 404:
            # Model deprecated / not found - permanent
            raise ProviderError(
                provider="omniroute",
                model=model,
                status_code=404,
                message="Requested model is unavailable.",
                retryable=False,
                permanent=True,
            )

        if resp.status_code in (429, 402, 503):
            # Rate limit / payment required / service unavailable - retry later
            raise ProviderError(
                provider="omniroute",
                model=model,
                status_code=resp.status_code,
                message="OmniRoute is temporarily unavailable.",
                retryable=True,
            )

        if resp.status_code in (401, 403):
            # Auth problem - not the model's fault, but nothing we can do
            raise ProviderError(
                provider="omniroute",
                model=model,
                status_code=resp.status_code,
                message="OmniRoute authentication or authorization failed.",
                retryable=False,
            )

        # Any other status - generic error
        raise ProviderError(
            provider="omniroute",
            model=model,
            status_code=resp.status_code,
            message="OmniRoute returned an unexpected HTTP error.",
            retryable=False,
        )


def _parse_success(data: dict, model: str) -> Completion:
    """Convert OmniRoute's OpenAI-style response into our Completion."""
    choices = data.get("choices", [])
    if not choices:
        raise ProviderError(
            provider="omniroute",
            model=model,
            status_code=200,
            message="Empty choices array in response",
            retryable=False,
        )

    text = choices[0].get("message", {}).get("content", "") or ""
    usage = data.get("usage", {}) or {}

    return Completion(
        text=text,
        model=data.get("model", model),
        provider="omniroute",
        prompt_tokens=usage.get("prompt_tokens", 0) or 0,
        completion_tokens=usage.get("completion_tokens", 0) or 0,
        total_tokens=usage.get("total_tokens", 0) or 0,
        cached=False,
        raw=data,
    )


def _extract_error_message(resp) -> str:
    """
    Pull a useful diagnostic string out of a failed HTTP response.

    This function is intended for server-side logging only.
    Its output must never be treated as user-facing text.
    """
    try:
        body = resp.json()
    except (ValueError, json.JSONDecodeError):
        return resp.text[:200] if resp.text else "(no body)"

    if isinstance(body, dict):
        # Common shapes: {"error": {"message": "..."}} or {"error": "..."}
        err = body.get("error")
        if isinstance(err, dict):
            return str(err.get("message", err))[:200]
        if err:
            return str(err)[:200]

        # Some providers: {"message": "..."}
        if "message" in body:
            return str(body["message"])[:200]

    return json.dumps(body)[:200]


def ping(model: str) -> Optional[str]:
    """
    Send a tiny test message to verify the model responds.
    Returns the model's reply text on success, None on any failure.
    Used at startup for model validation.
    """
    try:
        completion = call(
            model=model,
            messages=[Message(role="user", content="Say OK")],
            max_tokens=10,
            temperature=0.0,
        )
        return completion.text.strip()
    except ProviderError as e:
        logger.debug(
            "Ping failed for model=%s status=%s retryable=%s permanent=%s",
            model,
            e.status_code,
            e.retryable,
            e.permanent,
        )
        return None
    except Exception as e:
        logger.debug(
            "Ping unexpected error for model=%s: %s",
            model,
            e,
            exc_info=True,
        )
        return None