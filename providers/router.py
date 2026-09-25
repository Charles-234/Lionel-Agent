"""
Lionel Agent - Provider router with failover and cooldowns.

Tries entries in the routing table in order. Skips dead models.
Applies cooldowns based on error classification.
"""
import logging
import time
from typing import Dict, List, Optional, Tuple

import config
from providers.types import Message, Completion, ProviderError

logger = logging.getLogger(__name__)

# Cooldown durations (seconds)
COOLDOWN_RATE_LIMIT = 86400     # 24h for 429/402
COOLDOWN_UNAVAILABLE = 900      # 15min for 503
COOLDOWN_NETWORK = 300          # 5min for network errors
COOLDOWN_PERMANENT = float('inf')


class RouterState:
    """Tracks which models are dead and for how long."""

    def __init__(self):
        # key: (source, provider, model) tuple -> expiry timestamp
        self.dead_until: Dict[Tuple[str, str, str], float] = {}

    @staticmethod
    def _key(entry: dict) -> Tuple[str, str, str]:
        return (
            entry.get("source", ""),
            entry.get("provider", ""),
            entry.get("model", ""),
        )

    def is_dead(self, entry: dict) -> Tuple[bool, Optional[str]]:
        """Returns (is_dead, reason)."""
        key = self._key(entry)
        expiry = self.dead_until.get(key)
        if expiry is None:
            return False, None

        now = time.time()
        if now >= expiry:
            # Cooldown expired
            del self.dead_until[key]
            return False, None

        remaining = expiry - now
        if remaining == float('inf'):
            return True, "permanently dead"
        return True, f"cooldown {int(remaining)}s remaining"

    def mark_dead(self, entry: dict, seconds: float, reason: str):
        """Mark entry as dead for N seconds. Use COOLDOWN_PERMANENT for forever."""
        key = self._key(entry)
        self.dead_until[key] = time.time() + seconds if seconds != float('inf') else float('inf')
        label = "PERMANENT" if seconds == float('inf') else f"{int(seconds)}s"
        logger.warning(f"Router: marking {key} dead ({label}) - {reason}")

    def state(self) -> Dict[str, str]:
        """Returns a readable snapshot of current dead models."""
        out = {}
        now = time.time()
        for key, expiry in list(self.dead_until.items()):
            if now >= expiry:
                del self.dead_until[key]
                continue
            label = "permanent" if expiry == float('inf') else f"{int(expiry - now)}s"
            out[f"{key[0]}/{key[1] or '-'}/{key[2]}"] = label
        return out


# Global router state (in-process)
_state = RouterState()


def _classify_for_cooldown(error: ProviderError) -> Tuple[float, str]:
    """
    Returns (cooldown_seconds, reason) based on the error.
    """
    status = error.status_code

    # Permanent: model doesn't exist, auth broken
    if status in (400, 401, 403, 404):
        return COOLDOWN_PERMANENT, f"http {status}"

    # Rate limit / payment - long cooldown
    if status in (402, 429):
        return COOLDOWN_RATE_LIMIT, f"http {status}"

    # Provider unavailable - short cooldown
    if status == 503:
        return COOLDOWN_UNAVAILABLE, "http 503"

    # Network / timeout
    if status is None:
        return COOLDOWN_NETWORK, "network error"

    # Anything else - medium cooldown
    return COOLDOWN_UNAVAILABLE, f"http {status}"


def _call_omniroute(model: str, messages: List[Message], max_tokens: int, temperature: float) -> Completion:
    """Call via OmniRoute gateway."""
    from providers import omniroute
    return omniroute.call(model, messages, max_tokens=max_tokens, temperature=temperature)


def _call_litellm(model: str, messages, max_tokens: int, temperature: float):
    from providers import litellm_group
    return litellm_group.call_litellm(messages, max_tokens, temperature)


def _call_direct(provider: str, model: str, messages: List[Message], max_tokens: int, temperature: float) -> Completion:
    """Call direct provider client."""
    from providers import direct
    if provider == "groq":
        return direct.call_groq(model, messages, max_tokens=max_tokens, temperature=temperature)
    if provider == "gemini":
        return direct.call_gemini(model, messages, max_tokens=max_tokens, temperature=temperature)
    if provider == "cloudflare":
        return direct.call_cloudflare(model, messages, max_tokens=max_tokens, temperature=temperature)
    if provider == "huggingface":
        return direct.call_huggingface(model, messages, max_tokens=max_tokens, temperature=temperature)
    if provider == "local":
        return direct.call_openai_compatible(
            model,
            messages,
            base_url=config.LOCAL_LLM_URL,
            api_key=config.LOCAL_LLM_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    raise ProviderError(
        provider=provider, model=model, status_code=None,
        message=f"Unknown direct provider: {provider}",
        retryable=False, permanent=True,
    )


def call_with_failover(
    task_type: str,
    messages: List[Message],
    max_tokens: int = 2000,
    temperature: float = 0.7,
) -> Completion:
    """
    Main entry point. Iterates the routing table, skips dead models,
    tries each, applies cooldowns on failure.
    """
    if task_type not in config.ROUTING:
        raise ValueError(f"Unknown task type: {task_type}. Known: {list(config.ROUTING.keys())}")

    entries = config.ROUTING[task_type]
    attempts = []

    for entry in entries:
        source = entry.get("source")
        provider = entry.get("provider", "-")
        model = entry.get("model")
        label = f"{source}/{provider}/{model}" if source == "direct" else f"{source}/{model}"

        # Skip dead models
        dead, reason = _state.is_dead(entry)
        if dead:
            logger.info(f"Router: skipping {label} ({reason})")
            attempts.append(f"{label}: skipped ({reason})")
            continue

        logger.info(f"Router: trying {label}")

        try:
            if source == "omniroute":
                completion = _call_omniroute(model, messages, max_tokens, temperature)
            elif source == "direct":
                completion = _call_direct(provider, model, messages, max_tokens, temperature)
            elif source == "litellm":
                completion = _call_litellm(model, messages, max_tokens, temperature)
            else:
                logger.error(f"Router: unknown source '{source}' for {label}")
                continue

            logger.info(f"Router: SUCCESS via {label}")
            return completion

        except ProviderError as e:
            cooldown, reason = _classify_for_cooldown(e)
            _state.mark_dead(entry, cooldown, reason)
            attempts.append(f"{label}: {reason} ({e.message[:80]})")
            continue

        except Exception as e:
            # Unexpected error - treat as network, short cooldown
            _state.mark_dead(entry, COOLDOWN_NETWORK, f"unexpected: {type(e).__name__}")
            logger.error(f"Router: unexpected error on {label}: {e}")
            attempts.append(f"{label}: unexpected {type(e).__name__}")
            continue

    # All entries failed or were dead
    summary = "\n  - ".join(attempts) if attempts else "(no attempts made)"
    raise ProviderError(
        provider="router", model=f"task={task_type}", status_code=None,
        message=f"All providers for '{task_type}' failed or are in cooldown:\n  - {summary}",
        retryable=True,
    )


def router_state() -> Dict[str, str]:
    """Return a snapshot of dead models. Useful for /status command."""
    return _state.state()


def reset() -> None:
    """Clear all cooldowns. Useful for testing."""
    _state.dead_until.clear()