"""Quick test of the hybrid retriever (embeddings + BM25)."""
from skills import retriever

# Show what the retriever is actually using
r = retriever.get_retriever()
print(f"Retriever loaded: {len(r.skills)} skills")
print(f"Embeddings ready: {r.embeddings_ready}")
if r.embeddings is not None:
    print(f"Embeddings shape: {r.embeddings.shape}")
else:
    print(f"Embeddings: None")
print()

queries = [
    "how do I scan for open ports",
    "memory forensics volatility",
    "what is the difference between TCP and UDP",
    "malware analysis reverse engineering",
    "design UI frontend",
    "budget planning for a project",
]

for query in queries:
    print("=" * 70)
    print(f"Query: {query!r}")
    print("=" * 70)
    matches = retriever.search(query, top_k=5)
    if not matches:
        print("  (no matches above threshold)")
    else:
        for m in matches:
            cat = "[CAT]" if m.category_boosted else "     "
            print(f"  {m.score:6.2f} {cat} [{m.method:5s}] [{m.source:9s}] {m.name}")
    print()