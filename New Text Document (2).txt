"""LiteLLM group for free-tier failover."""
import os
from litellm import Router

_router = None

def get_litellm_router():
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

def call_litellm(messages, max_tokens, temperature):
    """Call through LiteLLM with its own internal failover."""
    from providers.types import Completion
    router = get_litellm_router()
    response = router.completion(
        model="llm7",
        messages=[{"role": m.role, "content": m.content} for m in messages],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content
    return Completion(
        text=text,
        model="litellm",
        provider="litellm-group",
        total_tokens=response.usage.total_tokens if response.usage else 0,
    )