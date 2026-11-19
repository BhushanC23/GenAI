# KubeCoach — Checkpoint 2 Live Demo Guide

**Project:** KubeCoach (Project ID: SJ-58, Theme: Developer Tools)  
**Student:** Bhushan Kailas Chaturbhuj (Reg. No: 2125PCAM1038)  
**Objective:** Live end-to-end demonstration of grounded RAG, verifiable citations, honest out-of-scope refusal (Q6), LangGraph Agent Mode with human approval, persistent feedback, and KubeCoach's signature **Kubernetes Object Relationship Strip**.

---

## 1. Application Startup Commands

Open **two terminals** in the `GenAI` repository root (`c:\Users\bhushan chaturbhuj\Desktop\KubeCoach\GenAI`).

### Terminal 1 — Start the FastAPI Backend
```powershell
# Activate virtual environment (Python 3.11+ recommended for LangGraph)
.\.venv311\Scripts\Activate.ps1

# Start FastAPI on http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Verify backend readiness:
- Health endpoint: `http://127.0.0.1:8000/health` (returns `status: "ok"`, `records_count: 18`)
- Swagger docs: `http://127.0.0.1:8000/docs`

### Terminal 2 — Start the Streamlit UI
```powershell
.\.venv311\Scripts\Activate.ps1

# Optional: configure custom backend URL (defaults to http://127.0.0.1:8000)
$env:API_BASE_URL="http://127.0.0.1:8000"

# Launch Streamlit UI on http://127.0.0.1:8501
streamlit run ui/app.py
```

---

## 2. Open the Streamlit UI & Verify Connection

1. Open **`http://127.0.0.1:8501`** in Chrome/Edge.
2. Point out the **Sidebar → Backend Status** indicator:
   - Shows **Connected · 18 records** (live verified via `GET /health`).
   - Show the **RAG Mode (/ask)** vs. **Agent Mode (/agent)** toggle, **New Chat** button, and empty-state **Suggested Questions**.

---

## 3. Live Demo Walkthrough (Step-by-Step)

### Demo Step 1 — Answerable Kubernetes Question + Signature Feature
- **Mode:** `RAG Mode (/ask)`
- **Prompt (click starter button or type):**
  > `What is the difference between a Pod and a Deployment?`
- **What to highlight:**
  1. Grounded plain-English explanation retrieved directly from persistent ChromaDB (`data/chroma_db`).
  2. **Signature Feature — Kubernetes Object Relationship Strip** rendered directly below the answer:
     `Deployment → ReplicaSet → Pods` (with `Deployment` and `Pods` highlighted, hover tooltips, and concise role legend).
  3. **Verified Documentation Sources** panel showing clickable official `kubernetes.io` URLs and source file (`deployment.md` / `pods.md`).
  4. Click **👍 Helpful** under the answer to demonstrate persistent feedback saved to `data/feedback.json` via `POST /feedback` (and duplicate prevention).

### Demo Step 2 — Citations & Networking Relationship Demonstration
- **Mode:** `RAG Mode (/ask)`
- **Prompt:**
  > `Explain Kubernetes Services with an example.`
- **What to highlight:**
  1. Clickable official citation pointing to `https://kubernetes.io/docs/concepts/services-networking/service/` (`service.md`).
  2. Relationship strip automatically adapts to the actual objects discussed: `Service → Pods` (or `Deployment → ReplicaSet → Pods ← Service` when comparing Deployment + Service exposure).
  3. Formatted Markdown with syntax-highlighted `kubectl` command blocks.

### Demo Step 3 — Original Unanswerable Question (Q6 Hallucination Guardrail)
- **Mode:** `RAG Mode (/ask)`
- **Prompt (exact Q6 from `eval/eval_set.json`):**
  > `How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?`
- **What to highlight:**
  1. KubeCoach refuses honestly: *"I don't know based on the provided official Kubernetes documentation..."*
  2. **Sources panel** displays *"No verified official Kubernetes documentation source covers this topic."* (**0 fabricated citations**).
  3. **Object Relationship Strip** is intentionally **omitted** so unrelated objects are never fabricated.

### Demo Step 4 — Agent Mode with Tool Selection & Human Approval (HITL)
- Switch sidebar mode to **`Agent Mode (/agent)`**.
- **Prompt:**
  > `Compare 1Gi and 1G memory`
- **What to highlight:**
  1. LangGraph `reasoning_node` selects `k8s_quantity_converter` (project-card assigned tool for SJ-58).
  2. LangGraph `approval_node` pauses execution via official `interrupt()` and displays the **Human Approval Required** card with exact tool name (`k8s_quantity_converter`) and exact JSON arguments (`{"quantity": "1Gi", "compare_to": "1G"}`).
  3. Click **Approve & Execute** (calls `POST /agent/approve` $\rightarrow$ `Command(resume={"approved": True})`).
  4. Deterministic `decimal.Decimal` output explains `1Gi` (`1,073,741,824 bytes`, binary SI) vs. `1G` (`1,000,000,000 bytes`, decimal SI) with exact `73,741,824 bytes` (`70.3257 Mi`) difference.
  5. Open **Agent Tool Execution & Trace** expander to show the exact LangGraph node transition trace (`reasoning_node → approval_node → tool_execution_node → reasoning_node → final_response_node`).

---

## 4. Viva Talking Points — Explaining the Architecture

### A. RAG Architecture (`app/rag.py` + `POST /ask`)
1. **Frontend isolation:** Streamlit (`ui/app.py`) contains zero LLM, RAG, or vector DB logic — it communicates strictly with FastAPI via HTTP (`ui/api_client.py`).
2. **Retrieval:** FastAPI encodes the user's question into a dense vector (`app/embed.py`) and queries persistent ChromaDB (`app/vectorstore.py`) for the top-$k$ most semantically similar chunks.
3. **Context Sufficiency Guardrail (`is_context_sufficient`):** Evaluates cosine similarity threshold ($S \ge 0.55$) and entity coverage before generation. Out-of-scope technologies (like Istio in Q6) are caught mathematically and answered with an honest refusal and zero citations.
4. **Grounded Generation:** Retrieved chunks are formatted into numbered context blocks with source URLs and passed to the Day 6 LLM provider wrapper (`app/llm.py`, supporting Groq, Gemini, and deterministic local fallback).

### B. Chunking, Embeddings & Retrieval (`app/chunking.py`, `app/embed.py`, `app/vectorstore.py`)
- **Chunking:** Official Kubernetes raw Markdown docs (`pods.md`, `deployment.md`, `service.md`, `ingress.md`, `configmap.md`, `namespaces.md`) plus 18 verified records (`data/records.json`) are cleaned of Hugo shortcodes and split using sliding-window overlap chunking into **435 chunks** with deterministic IDs (`doc:pods:chunk:001`) and preserved metadata (`title`, `source`, `page`, `category`).
- **Embeddings:** `sentence-transformers` model **`all-MiniLM-L6-v2`** encodes each chunk and query into a **384-dimensional** dense vector capturing semantic meaning (so conceptual queries like *"exposing deployment externally"* match Ingress/Service chunks even without exact keyword overlap).
- **Vector Store:** Persistent local **ChromaDB** (`data/chroma_db/`) indexed with HNSW Cosine space (`hnsw:space="cosine"`) and idempotent upserts preventing duplicates.

### C. Evaluation Results (`eval/eval_set.json` & `eval/rag_comparison.md`)
- Evaluated across **15 benchmark questions** (14 answerable Kubernetes questions + Q6 unanswerable Istio mTLS):
  - **Config A** (`500` chars, `100` overlap, `top_k=3`, 435 chunks): **86.7%** retrieval relevance, **93.3%** citation correctness, **100%** Q6 refusal, **29.6 ms** avg latency.
  - **Config B** (`800` chars, `150` overlap, `top_k=5`, 275 chunks): **86.7%** retrieval relevance, **100.0%** citation correctness, **100%** Q6 refusal, **24.6 ms** avg latency (**Winner** — higher citation completeness and faster retrieval).
- **Automated Quality Gate:** Over **120+ unit and integration tests** (`python -m unittest discover tests -v`) covering data models, ingestion, FastAPI routes, TF-IDF search, LLM wrapper, chunking, embeddings, ChromaDB, RAG, Decimal quantity converter, LangGraph interrupt/resume + `MemorySaver`, feedback persistence, and Streamlit UI.
