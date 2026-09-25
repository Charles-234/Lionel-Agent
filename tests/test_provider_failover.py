from unittest.mock import patch

import pytest

from providers import router
from providers.types import Completion, Message, ProviderError


def test_router_tries_next_provider_after_failure():
    router.reset()
    entries = [
        {"source": "direct", "provider": "first", "model": "model-a"},
        {"source": "direct", "provider": "second", "model": "model-b"},
    ]
    success = Completion(text="ok", model="model-b", provider="second")

    def call(provider, model, messages, max_tokens, temperature):
        if provider == "first":
            raise ProviderError(provider, model, 503, "unavailable", retryable=True)
        return success

    with patch.object(router.config, "ROUTING", {"chat": entries}), patch.object(router, "_call_direct", side_effect=call):
        result = router.call_with_failover("chat", [Message(role="user", content="hello")])

    assert result is success
    assert router.router_state()["direct/first/model-a"]
    router.reset()
