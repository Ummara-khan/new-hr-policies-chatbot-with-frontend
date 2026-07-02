"""
ingest.py  v3
- Uses __file__-relative paths so it works regardless of cwd
- Reads both .txt and .pdf
- Verbose per-file logging
- Clears stale DB if DATA_DIR changed
"""

import os, hashlib, sys
from pathlib import Path
from typing import List, Dict

# Resolve paths relative to THIS file, not cwd
THIS_DIR   = Path(__file__).parent.resolve()
DEFAULT_DATA  = (THIS_DIR.parent / "data").resolve()
DEFAULT_CHROMA = (THIS_DIR / "chroma_db").resolve()

CHUNK_SIZE    = 600
CHUNK_OVERLAP = 120
EMBED_MODEL   = "all-MiniLM-L6-v2"
COLLECTION    = "company_policies"
DEPARTMENTS   = ["garment", "denim", "corporate"]
POLICY_TYPES  = ["hr", "medical", "leave", "security"]


def _resolve(env_val: str, default: Path) -> Path:
    """Resolve a path: if absolute use as-is, else relative to THIS_DIR."""
    if not env_val:
        return default
    p = Path(env_val)
    if p.is_absolute():
        return p.resolve()
    return (THIS_DIR / p).resolve()


def extract_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_pdf(path: Path) -> str:
    try:
        import pdfplumber
        pages = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    pages.append(t)
        return "\n\n".join(pages)
    except Exception as e:
        print(f"    [PDF-WARN] {path.name}: {e}")
        return ""


def chunk_text(text: str) -> List[str]:
    chunks, start = [], 0
    text = text.strip()
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        c = text[start:end].strip()
        if len(c) > 30:          # skip tiny fragments
            chunks.append(c)
        if end >= len(text):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def build_index(data_dir: str = None, chroma_dir: str = None) -> int:
    """
    Ingest all policy files into ChromaDB.
    Returns total chunk count.
    """
    from sentence_transformers import SentenceTransformer
    import chromadb

    data_path   = _resolve(data_dir   or os.getenv("DATA_DIR", ""),   DEFAULT_DATA)
    chroma_path = _resolve(chroma_dir or os.getenv("CHROMA_PERSIST_DIR", ""), DEFAULT_CHROMA)

    print(f"[Ingest] DATA DIR  : {data_path}")
    print(f"[Ingest] CHROMA DIR: {chroma_path}")

    if not data_path.exists():
        print(f"[Ingest] ERROR: data directory not found: {data_path}", file=sys.stderr)
        return 0

    chroma_path.mkdir(parents=True, exist_ok=True)

    print(f"[Ingest] Loading embedding model: {EMBED_MODEL}")
    embedder   = SentenceTransformer(EMBED_MODEL)
    client     = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    new_chunks = 0
    found_files = 0

    for dept in DEPARTMENTS:
        for ptype in POLICY_TYPES:
            folder = data_path / dept / ptype
            if not folder.exists():
                continue
            for fpath in sorted(folder.glob("*")):
                if fpath.suffix.lower() not in (".txt", ".pdf"):
                    continue
                found_files += 1
                fhash  = file_hash(fpath)
                marker = f"__marker__{dept}__{ptype}__{fpath.name}__{fhash}"

                if collection.get(ids=[marker], include=[])["ids"]:
                    print(f"  SKIP (unchanged): {dept}/{ptype}/{fpath.name}")
                    continue

                print(f"  Ingesting: {dept}/{ptype}/{fpath.name}")
                raw = extract_pdf(fpath) if fpath.suffix.lower() == ".pdf" else extract_txt(fpath)
                if not raw.strip():
                    print(f"    [WARN] Empty — skipping")
                    continue

                chunks = chunk_text(raw)
                if not chunks:
                    print(f"    [WARN] No chunks produced — skipping")
                    continue

                ids, docs, metas = [], [], []
                for i, chunk in enumerate(chunks):
                    ids.append(f"{dept}__{ptype}__{fpath.stem}_{fpath.suffix[1:]}__{i}")
                    docs.append(chunk)
                    metas.append({
                        "department":  dept,
                        "policy_type": ptype,
                        "source":      fpath.name,
                        "file_type":   fpath.suffix[1:].lower(),
                        "chunk_index": i,
                        "is_marker":   False,
                    })

                embeddings = embedder.encode(docs, show_progress_bar=False).tolist()
                collection.upsert(ids=ids, documents=docs,
                                  embeddings=embeddings, metadatas=metas)

                # write marker
                collection.upsert(
                    ids=[marker],
                    documents=[f"MARKER:{fpath.name}"],
                    embeddings=[embedder.encode("marker").tolist()],
                    metadatas=[{"department": dept, "policy_type": ptype,
                                "source": fpath.name, "is_marker": True}],
                )
                new_chunks += len(chunks)
                print(f"    → {len(chunks)} chunks stored")

    total = collection.count()
    print(f"[Ingest] Files scanned: {found_files} | New chunks: {new_chunks} | DB total: {total}")
    return total


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    build_index()
