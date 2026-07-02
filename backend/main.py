"""
main.py  v3
- /diagnose endpoint to debug retrieval issues
- Absolute path env resolution
- No department selection needed from user
"""

import os, json, asyncio
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env from same directory as this file
THIS_DIR = Path(__file__).parent.resolve()
load_dotenv(THIS_DIR / ".env")

from ingest     import build_index, THIS_DIR as INGEST_DIR, DEFAULT_DATA, DEFAULT_CHROMA
from retriever  import get_retriever
from classifier import detect
from llm        import get_llm


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[Startup] Running ingestion check…")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, build_index)
    print("[Startup] Ready.")
    yield


app = FastAPI(title="Company Policy Chatbot API", version="3.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Pydantic models ─────────────────────────────────────────────────────────

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []
    department:  Optional[str] = None   # optional override
    policy_type: Optional[str] = None   # optional override

class ChatResponse(BaseModel):
    answer:               str
    sources:              List[str]
    departments:          List[str]
    policy_types:         List[str]
    detected_department:  Optional[str]
    detected_policy_type: Optional[str]
    hits_count:           int


# ── Core ────────────────────────────────────────────────────────────────────

def run_rag(req: ChatRequest):
    detected  = detect(req.message)
    dept      = req.department  or detected["department"]   # None = search all
    ptype     = req.policy_type or detected["policy_type"]  # None = search all

    retriever = get_retriever()
    hits      = retriever.search(req.message, department=dept, policy_type=ptype, top_k=6)
    history   = [{"role": m.role, "content": m.content} for m in req.history]
    return hits, history, dept, ptype


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    r = get_retriever()
    return {"status": "ok", "db_chunks": r.collection.count(),
            "model": os.getenv("GROQ_MODEL","llama3-70b-8192")}


@app.get("/diagnose")
def diagnose():
    """Debug endpoint — shows exactly what's in the DB and tests a sample search."""
    r = get_retriever()
    total = r.collection.count()

    # Sample items from DB
    sample = r.collection.peek(10) if total > 0 else {"ids":[],"documents":[],"metadatas":[]}
    non_markers = [
        {"id": sid, "dept": m.get("department"), "ptype": m.get("policy_type"),
         "src": m.get("source"), "preview": d[:80]}
        for sid, d, m in zip(sample["ids"], sample["documents"], sample["metadatas"])
        if not m.get("is_marker")
    ]

    # Test search
    test_hits = r.search("maternity leave days garment", top_k=3)

    return {
        "db_total_items": total,
        "chroma_path": str(DEFAULT_CHROMA),
        "data_path":   str(DEFAULT_DATA),
        "sample_non_marker_docs": non_markers,
        "test_search_maternity": [
            {"dept": h["department"], "ptype": h["policy_type"],
             "score": h["score"], "src": h["source"], "preview": h["text"][:120]}
            for h in test_hits
        ],
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    hits, history, dept, ptype = run_rag(req)
    result = get_llm().chat(req.message, history, hits)
    return ChatResponse(
        answer=result["answer"], sources=result["sources"],
        departments=result["departments"], policy_types=result["policy_types"],
        detected_department=dept, detected_policy_type=ptype,
        hits_count=len(hits),
    )


@app.post("/stream-chat")
async def stream_chat(req: ChatRequest):
    hits, history, dept, ptype = run_rag(req)
    llm = get_llm()

    async def gen():
        loop   = asyncio.get_event_loop()
        tokens = await loop.run_in_executor(
            None, lambda: list(llm.stream_chat(req.message, history, hits)))
        for kind, val in tokens:
            if kind == "token":
                yield f"data: {json.dumps({'token': val})}\n\n"
            else:
                yield f"data: {json.dumps({'done': True, **val, 'detected_department': dept, 'detected_policy_type': ptype, 'hits_count': len(hits)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/ingest")
async def ingest():
    loop = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, build_index)
    return {"status": "done", "db_total": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
