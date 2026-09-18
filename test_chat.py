"""Test Mode 4 - skill-assisted chat."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from agent.chat import chat
from providers import token_budget
from memory import history


def main():
    user_id = 0

    print("=" * 70)
    print("CHAT MODE TEST")
    print("=" * 70)
    print(f"Budget: {token_budget.stats(user_id)}")
    print()

    # Test 1: skill-assisted query
    print("=" * 70)
    print("TEST 1: skill-assisted chat")
    print("=" * 70)
    q1 = "How do I analyze a memory dump for malware?"
    print(f"> {q1}")
    r1 = chat(user_id, q1)
    print()
    print(r1.text[:1500])
    print()
    print(f"[{r1.provider}/{r1.model} | {r1.tokens_used} tokens]")
    print(f"[skills used: {r1.skills_used}]")
    print()

    # Test 2: general chat
    print("=" * 70)
    print("TEST 2: general chat (no strong skill match)")
    print("=" * 70)
    q2 = "What's the difference between TCP and UDP in one sentence?"
    print(f"> {q2}")
    r2 = chat(user_id, q2)
    print()
    print(r2.text[:800])
    print()
    print(f"[{r2.provider}/{r2.model} | {r2.tokens_used} tokens]")
    print()

    # Budget after
    print("=" * 70)
    print("BUDGET AFTER TESTS")
    print("=" * 70)
    print(token_budget.stats(user_id))

    # History
    print()
    print("=" * 70)
    print("HISTORY (last 4 turns)")
    print("=" * 70)
    for t in history.get(user_id).recent(limit=4):
        print(f"[{t.role}] {t.content[:100]}")


if __name__ == "__main__":
    main()