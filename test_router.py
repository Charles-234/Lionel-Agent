"""
Test the router end-to-end.
"""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from providers.types import Message, ProviderError
from providers import router


def main():
    print("=" * 70)
    print("Router Test - Chat Task")
    print("=" * 70)

    messages = [
        Message(role="user", content="In one sentence, what is the capital of France?"),
    ]

    try:
        completion = router.call_with_failover(
            task_type="chat",
            messages=messages,
            max_tokens=200,
            temperature=0.7,
        )
        print()
        print(f"Reply: {completion.text}")
        print(f"Model used: {completion.provider} / {completion.model}")
        print(f"Tokens: {completion.total_tokens}")
    except ProviderError as e:
        print()
        print(f"ALL FAILED: {e.message}")

    print()
    print("=" * 70)
    print("Router state after test:")
    print("=" * 70)
    state = router.router_state()
    if not state:
        print("  (nothing marked dead)")
    else:
        for model, status in state.items():
            print(f"  {model}: {status}")


if __name__ == "__main__":
    main()