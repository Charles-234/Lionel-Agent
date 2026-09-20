"""
Quick test: can we talk to OmniRoute?
Run: python test_omniroute.py
"""
import logging
import sys

import config
from providers.types import Message, ProviderError
from providers import omniroute

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("test")


def main():
    print("Lionel - OmniRoute connectivity test")
    print(f"URL: {config.OMNIROUTE_URL}")
    print("Credential: configured (value hidden)")
    print()

    # Test 1 - ping Cerebras (chat primary)
    print("[Test 1] Cerebras gpt-oss-120b (chat primary)")
    reply = omniroute.ping("cerebras/gpt-oss-120b")
    if reply:
        print(f"  OK - replied: {reply!r}")
    else:
        print("  FAILED")
    print()

    # Test 2 - a real message with token counts
    print("[Test 2] Real message with token tracking")
    try:
        completion = omniroute.call(
            model="cerebras/gpt-oss-120b",
            messages=[
                Message(role="system", content="You are Lionel. Reply in one sentence."),
                Message(role="user", content="Introduce yourself in one sentence."),
            ],
            max_tokens=100,
            temperature=0.7,
        )
        print(f"  Text: {completion.text}")
        print(f"  Model used: {completion.model}")
        print(
            f"  Tokens - prompt: {completion.prompt_tokens}, "
            f"completion: {completion.completion_tokens}, "
            f"total: {completion.total_tokens}"
        )
    except ProviderError as e:
        print("  FAILED: OmniRoute request could not be completed.")
        print(f"  Status code: {e.status_code}")
        print(f"  Retryable: {e.retryable}, Permanent: {e.permanent}")
        sys.exit(1)
    print()

    # Test 3 - fallback 1 (Groq)
    print("[Test 3] Groq llama-3.3-70b (chat fallback 1)")
    reply = omniroute.ping("groq/llama-3.3-70b-versatile")
    if reply:
        print(f"  OK - replied: {reply!r}")
    else:
        print("  FAILED")
    print()

    # Test 4 - fallback 2 (SambaNova)
    print("[Test 4] SambaNova llama-3.3-70b (chat fallback 2)")
    reply = omniroute.ping("sambanova/Meta-Llama-3.3-70B-Instruct")
    if reply:
        print(f"  OK - replied: {reply!r}")
    else:
        print("  FAILED")
    print()

    print("Done.")


if __name__ == "__main__":
    main()