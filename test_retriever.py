"""Test the skill retriever with sample queries."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

from skills import retriever


def show_results(query: str, top_k: int = 5):
    print()
    print("=" * 70)
    print(f"Query: {query!r}")
    print("=" * 70)
    matches = retriever.search(query, top_k=top_k)
    if not matches:
        print("  (no matches)")
        return
    for i, m in enumerate(matches, 1):
        print(f"{i}. [{m.source}] {m.name}  (score: {m.score:.2f})")
        print(f"   category: {m.category or '(none)'}")
        print(f"   {m.description[:150]}...")
        print()


def main():
    print("=" * 70)
    print("RETRIEVER SMOKE TEST")
    print("=" * 70)

    r = retriever.get_retriever()
    print(f"Total skills: {len(r.skills)}")
    print(f"Sources: {r.list_sources()}")
    print()

    # Test queries
    show_results("memory forensics volatility")
    show_results("web scraper python")
    show_results("malware analysis reverse engineering")
    show_results("design UI frontend")
    show_results("sql injection testing")

    # Category overview
    print("=" * 70)
    print("Categories (top 15):")
    print("=" * 70)
    cats = r.list_categories()
    for cat, count in sorted(cats.items(), key=lambda x: -x[1])[:15]:
        print(f"  {count:5d}  {cat}")


if __name__ == "__main__":
    main()