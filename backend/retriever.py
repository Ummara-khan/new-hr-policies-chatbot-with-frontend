"""
retriever.py  v3
- Absolute path resolution
- Verbose search logging
- Returns empty list (never crashes) so caller can detect and warn user
"""

import os
from pathlib import Path
from typing import List, Optional, Dict

THIS_DIR       = Path(__file__).parent.resolve()
DEFAULT_CHROMA = (THIS_DIR / "chroma_db").resolve()

EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION  = "company_policies"
TOP_K       = 6


class PolicyRetriever:
    def __init__(self, chroma_dir: str = None):
        from sentence_transformers import SentenceTransformer
        import chromadb

        path = Path(chroma_dir).resolve() if chroma_dir else DEFAULT_CHROMA
        print(f"[Retriever] Chroma path: {path}")

        self.embedder   = SentenceTransformer(EMBED_MODEL)
        self.client     = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"})

        total = self.collection.count()
        print(f"[Retriever] DB has {total} items")
        if total == 0:
            print("[Retriever] WARNING: DB is EMPTY — run ingest first!")

    def search(self, query: str,
               department:  Optional[str] = None,
               policy_type: Optional[str] = None,
               top_k: int = TOP_K) -> List[Dict]:

        total = self.collection.count()
        if total == 0:
            print("[Retriever] ERROR: collection is empty, cannot search")
            return []

        vec = self.embedder.encode(query).tolist()

        # Build filter — exclude markers
        where_clauses = [{"is_marker": {"$ne": True}}]
        if department:
            where_clauses.append({"department": {"$eq": department}})
        if policy_type:
            where_clauses.append({"policy_type": {"$eq": policy_type}})

        where = where_clauses[0] if len(where_clauses) == 1 else {"$and": where_clauses}

        # count how many non-marker docs match the filter
        n = min(top_k, max(total - 1, 1))

        print(f"[Retriever] query='{query[:60]}' dept={department} ptype={policy_type} n={n}")

        try:
            res = self.collection.query(
                query_embeddings=[vec], n_results=n,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            print(f"[Retriever] query error: {e}")
            return []

        hits = []
        if res["ids"] and res["ids"][0]:
            for doc, meta, dist in zip(
                res["documents"][0], res["metadatas"][0], res["distances"][0]
            ):
                if meta.get("is_marker"):
                    continue
                hits.append({
                    "text":        doc,
                    "department":  meta.get("department", ""),
                    "policy_type": meta.get("policy_type", ""),
                    "source":      meta.get("source", ""),
                    "file_type":   meta.get("file_type", ""),
                    "score":       round(1 - dist, 4),
                })

        print(f"[Retriever] → {len(hits)} hits returned")
        if hits:
            for h in hits[:3]:
                print(f"   [{h['department']}|{h['policy_type']}] score={h['score']} src={h['source']} | {h['text'][:60]!r}")

        return hits


_retriever: Optional[PolicyRetriever] = None


def get_retriever() -> PolicyRetriever:
    global _retriever
    if _retriever is None:
        chroma_env = os.getenv("CHROMA_PERSIST_DIR", "")
        chroma_dir = str(Path(chroma_env).resolve()) if chroma_env else str(DEFAULT_CHROMA)
        _retriever = PolicyRetriever(chroma_dir=chroma_dir)
    return _retriever
