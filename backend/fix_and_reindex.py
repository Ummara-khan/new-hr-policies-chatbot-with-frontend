#!/usr/bin/env python3
"""
fix_and_reindex.py
------------------
Run this script to diagnose and fix the ChromaDB index from scratch.
Usage:  python fix_and_reindex.py

It will:
1. Show resolved paths
2. Delete the old chroma_db (stale index)
3. Re-ingest all .txt and .pdf policy files
4. Verify by doing a test search
"""

import os, shutil, sys
from pathlib import Path
from dotenv import load_dotenv

THIS_DIR = Path(__file__).parent.resolve()
load_dotenv(THIS_DIR / ".env")

DATA_DIR_ENV   = os.getenv("DATA_DIR", "")
CHROMA_DIR_ENV = os.getenv("CHROMA_PERSIST_DIR", "")

def resolve(env_val, default):
    if not env_val:
        return default
    p = Path(env_val)
    return p.resolve() if p.is_absolute() else (THIS_DIR / p).resolve()

DATA_PATH   = resolve(DATA_DIR_ENV,   THIS_DIR.parent / "data")
CHROMA_PATH = resolve(CHROMA_DIR_ENV, THIS_DIR / "chroma_db")

print("=" * 60)
print("  POLICY CHATBOT — REINDEX TOOL")
print("=" * 60)
print(f"\n  Data directory : {DATA_PATH}")
print(f"  ChromaDB path  : {CHROMA_PATH}")

# 1. Check data directory
if not DATA_PATH.exists():
    print(f"\n❌ ERROR: Data directory not found: {DATA_PATH}")
    print("   Make sure your .env DATA_DIR points to the 'data' folder.")
    sys.exit(1)

txt_files = list(DATA_PATH.rglob("*.txt"))
pdf_files = list(DATA_PATH.rglob("*.pdf"))
print(f"\n  Found {len(txt_files)} .txt files and {len(pdf_files)} .pdf files")

if not txt_files and not pdf_files:
    print("\n❌ ERROR: No policy files found! Run generate_policies.py first:")
    print("   python generate_policies.py")
    sys.exit(1)

# 2. Wipe old DB
if CHROMA_PATH.exists():
    print(f"\n  Deleting old ChromaDB at {CHROMA_PATH}...")
    shutil.rmtree(CHROMA_PATH)
    print("  ✓ Old DB deleted")

# 3. Re-ingest
print("\n  Starting fresh ingestion...")
from ingest import build_index
total = build_index(str(DATA_PATH), str(CHROMA_PATH))

if total == 0:
    print("\n❌ ERROR: Ingestion produced 0 chunks. Check your data files.")
    sys.exit(1)

print(f"\n  ✓ Ingestion complete — {total} chunks in DB")

# 4. Test search
print("\n  Running test search: 'maternity leave garment' ...")
from retriever import PolicyRetriever
r = PolicyRetriever(chroma_dir=str(CHROMA_PATH))
hits = r.search("maternity leave garment", top_k=3)

if not hits:
    print("  ❌ Test search returned 0 results — something is wrong with embeddings.")
    sys.exit(1)

print(f"  ✓ Test search returned {len(hits)} hits:")
for h in hits:
    print(f"     [{h['department']}|{h['policy_type']}] score={h['score']} | {h['text'][:80]!r}")

print(f"\n{'=' * 60}")
print("  ✅ All good! Restart your server:")
print("     python main.py")
print(f"{'=' * 60}\n")
