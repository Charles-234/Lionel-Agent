"""Quick inspection of the master skill index."""
import json
import random
from collections import Counter


def main():
    with open("skills/master_index.json", "r", encoding="utf-8") as f:
        idx = json.load(f)

    print("=" * 60)
    print(f"Total skills: {idx['total']}")
    print(f"By source: {idx['by_source']}")
    print("=" * 60)
    print()

    # Category breakdown
    categories = Counter(s["category"] for s in idx["skills"] if s["category"])
    print(f"Top 15 categories (of {len(categories)} total):")
    for cat, count in categories.most_common(15):
        print(f"  {count:5d}  {cat}")
    print()

    # 3 random samples
    print("=" * 60)
    print("Random samples:")
    print("=" * 60)
    samples = random.sample(idx["skills"], min(3, len(idx["skills"])))
    for s in samples:
        print()
        print(f"[{s['source']}] {s['name']}")
        print(f"  category: {s['category']}")
        print(f"  description: {s['description'][:160]}...")
        print(f"  path: {s['path']}")


if __name__ == "__main__":
    main()