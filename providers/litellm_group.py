"""LiteLLM group for free-tier failover."""

from __future__ import annotations

import logging
import os
from typing import List

from litellm import Router

from providers.types import Completion, Message

logger = logging.getLogger(__name__)

_router = None


def get_litellm_router():
    """Build the LiteLLM router once and reuse it."""
    global _router
    if _router is None:
        _router = Router(
            model_list=[
                {
                    "model_name": "llm7",
                    "litellm_params": {
                        "model": "openai/default",
                        "api_base": "https://api.llm7.io/v1",
                        "api_key": "unused",
                    },
                },
                {
                    "model_name": "ovh",
                    "litellm_params": {
                        "model": "openai/Meta-Llama-3_3-70B-Instruct",
                        "api_base": "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1",
                        "api_key": os.environ.get("OVHCLOUD_API_KEY", ""),
                    },
                },
                {
                    "model_name": "ollama",
                    "litellm_params": {
                        "model": "ollama/llama3.2",
                        "api_base": "http://localhost:11434",
                        "api_key": "ollama",
                    },
                },
            ],
            fallbacks=[{"llm7": ["ovh", "ollama"]}],
            num_retries=1,
            timeout=30,
        )
    return _router


def call_litellm(
    messages: List[Message],
    max_tokens: int,
    temperature: float,
) -> Completion:
    """Call through LiteLLM with its own internal failover."""
    router = get_litellm_router()
    response = router.completion(
        model="llm7",
        messages=[
            {"role": m.role, "content": m.content}
            for m in messages
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content or ""
    total = 0
    if getattr(response, "usage", None):
        total = getattr(response.usage, "total_tokens", 0) or 0
    return Completion(
        text=text,
        model="litellm-group",
        provider="litellm",
        total_tokens=total,
    )
