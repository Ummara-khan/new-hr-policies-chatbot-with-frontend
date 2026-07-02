# 🏭 Company Policy Chatbot  v2

A full-stack RAG chatbot — **ask anything, no department selection required**.  
The bot automatically detects which department & policy type your question relates to.

---

## 📁 Project Structure

```
policy-chatbot/
├── data/
│   ├── garment/   hr/ medical/ leave/ security/   ← .txt + .pdf per policy
│   ├── denim/     hr/ medical/ leave/ security/
│   └── corporate/ hr/ medical/ leave/ security/
│
├── backend/
│   ├── generate_policies.py   ← Generates all 24 policy files (run once)
│   ├── ingest.py              ← Reads .txt + .pdf, chunks, embeds → ChromaDB
│   ├── retriever.py           ← Semantic search across ALL policies
│   ├── classifier.py          ← Auto-detects department + policy type from question
│   ├── llm.py                 ← Groq chat with streaming + memory
│   ├── main.py                ← FastAPI: /chat  /stream-chat  /ingest  /health
│   └── requirements.txt
│
└── frontend/
    └── src/  App.js  App.css  ← ChatGPT-style UI, no dept selection needed
```

---

## 🚀 Quick Start

### 1. Generate policy files (already done if using this zip)
```bash
cd backend
python generate_policies.py
```

### 2. Backend
```bash
cd backend
cp .env.example .env          # add GROQ_API_KEY
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py                # auto-ingests .txt + .pdf on startup
```

### 3. Frontend
```bash
cd frontend
npm install && npm start
```

---

## 🔑 `.env` file
```
GROQ_API_KEY=gsk_...          # free at console.groq.com
GROQ_MODEL=llama3-70b-8192
CHROMA_PERSIST_DIR=./chroma_db
DATA_DIR=../data
```

---

## 💬 How It Works (v2)

```
User: "What is the reimbursement process?"
         │
         ▼
  [Classifier]  keyword + Groq LLM
  → policy_type = "medical"
  → department  = None (not mentioned → search all)
         │
         ▼
  [ChromaDB]  search across garment + denim + corporate medical policies
         │
         ▼
  [Groq LLM]  answers with context from all matching docs
         │
         ▼
  Bot: "In the Garment department, claims must be submitted within 30 days...
        In Corporate, Grade 4+ get priority processing within 7 working days..."
  Sources: [medical_policy.txt, medical_policy.pdf]
  Dept badges: [GARMENT] [DENIM] [CORPORATE]
```

---

## 📄 Policy Files (24 total)

Each department × policy type has both:
- `hr_policy.txt`       — plain text with numbered lists, tables, phone directories
- `hr_policy.pdf`       — formatted PDF with coloured headers, tables, contact cards

**Rich content includes:**
- Numbered contact directories with phone numbers, extensions, emails
- Department-specific phone numbers (e.g., Chemical Spill Hotline Ext. 510)
- Approval matrices, penalty tables, coverage limit tables
- Step-by-step emergency procedures with numbered steps

---

## 🎨 Frontend Features

- **No department selection** — just type and ask
- **Auto-detects** which department(s) and policy area the answer comes from
- **Coloured dept badges** on each answer (👕 Garment / 👖 Denim / 🏢 Corporate)
- **Source file badges** showing which `.txt` / `.pdf` was used
- **6 quick suggestion buttons** on first load
- **Streaming responses** — tokens appear live
- **Multi-session sidebar** with history
- **Conversation memory** — "tell me more" works naturally
- **👍 / 👎 feedback** buttons

---

## ➕ Adding Policies

Drop any `.txt` or `.pdf` file into the right folder:
```
data/garment/hr/new_policy.txt
```
Then hit the API to re-ingest:
```bash
curl -X POST http://localhost:8000/ingest
```
Only new/changed files are re-embedded.
