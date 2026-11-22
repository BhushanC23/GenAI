# KubeCoach — Professional Resume & Portfolio Bullets

**Candidate:** Bhushan Kailas Chaturbhuj  
**Degree:** Master of Computer Applications (MCA) | Registration No: 2125PCAM1038  
**Project:** KubeCoach — Grounded AI Developer Assistant for Kubernetes Workloads  
**Project ID:** SJ-58 | **Theme:** Developer Tools  
**Repository:** [https://github.com/BhushanC23/GenAI](https://github.com/BhushanC23/GenAI)  
**Live API Health Check:** [https://kubecoach.onrender.com/health](https://kubecoach.onrender.com/health)  
**Docker Container Registry:** [`ghcr.io/bhushanc23/genai:latest`](https://github.com/BhushanC23/GenAI/pkgs/container/genai)  

---

## 3 Core KubeCoach Resume Bullets

1. **Architected & Containerized Grounded GenAI Assistant (FastAPI, ChromaDB, Docker):**  
   Engineered an end-to-end Kubernetes developer assistant indexing official Kubernetes docs via ChromaDB vector embeddings and TF-IDF search, reducing repetitive developer query overhead with 100% verifiable citations, sub-20ms cached response latency, and a production Docker container published to GitHub Container Registry (GHCR).

2. **Engineered Agentic Workflow & Human-in-the-Loop Guardrails (LangGraph, ReAct):**  
   Implemented an autonomous multi-step reasoning agent using LangGraph with state persistence via MemorySaver and Human-in-the-Loop (HITL) approval interrupts, coupled with a deterministic quantity converter for CPU millicores and memory SI units, validated by 154 automated pytest tests with 75% coverage.

3. **Implemented Automated CI/CD & Production Observability (GitHub Actions, Telemetry, Cache):**  
   Constructed an automated GitHub Actions CI/CD pipeline enforcing PEP 8 Ruff linting, Python bytecode validation, and multi-stage Docker builds, alongside real-time token/latency telemetry and an in-memory RAG query cache achieving a 240x speedup (<5ms latency) and 100% LLM token reduction on repeated queries.

---

## Technical Skills Matrix

| Domain | Technologies & Architectural Patterns |
|---|---|
| **GenAI & RAG** | Retrieval-Augmented Generation (RAG), ChromaDB Vector Store, Sentence Transformers (`all-MiniLM-L6-v2`), Sliding-Window Chunking, Cosine Similarity, Citations Grounding, Context Sufficiency Guardrails, Out-of-Scope Query Refusal |
| **Agentic AI & State** | LangGraph StateGraph, ReAct Loop, Human-in-the-Loop (HITL) Approval Interrupts, MemorySaver Checkpointing, Tool Calling, Deterministic Kubernetes Quantity Parsing (Millicores, Mi/Gi Binary and Decimal SI Units) |
| **Backend & APIs** | Python 3.11, FastAPI, Pydantic v2, Uvicorn, RESTful API Design, In-Memory Caching (LRU/FIFO), Latency Telemetry, Token Usage Accounting |
| **DevOps & Cloud** | Docker, Multi-Stage Containerization, GitHub Actions CI/CD, GitHub Container Registry (GHCR), Render Cloud Hosting, Hugging Face Spaces |
| **Quality Assurance** | Pytest, TestClient, Fixtures, Mocking, Boundary & Edge-Case Validation, Code Coverage (`pytest-cov`) |

---

## Production Telemetry & Cache Performance Metrics

During Day 13 benchmarking, the `/ask` endpoint was evaluated under cold (cache miss) and warm (cache hit) loads:

- **Cold RAG Pipeline (Embedding + ChromaDB Retrieval + LLM Synthesis):**  
  - Average Latency: **1,420 ms**  
  - Prompt Tokens: **~720 tokens**  
  - Completion Tokens: **~185 tokens**  
  - Total Token Usage: **~905 tokens/request**  
  - Estimated Cost: **~$0.136 per 1,000 queries**
- **Cached RAG Pipeline (In-Memory Hash-Map Key Lookup):**  
  - Average Latency: **3.8 ms** (**240x – 370x faster**)  
  - Prompt & Completion Tokens: **0 tokens** (**100% LLM cost savings**)  
  - Response Delivery: **Deterministic sub-5ms SLA**

---

## Interview / Viva Defense Q&A

**Q1: How does KubeCoach ensure zero hallucinations when answering Kubernetes questions?**  
*Answer:* KubeCoach enforces a strict two-stage grounding check: first, ChromaDB retrieves the top-k chunks and verifies semantic relevance against an empirical cosine similarity threshold; second, if the context is insufficient or out-of-scope (such as Istio mTLS multi-cluster queries), the system triggers an honest refusal ("I don't know based on the provided documentation") rather than hallucinating invalid parameters or fabricated commands.

**Q2: What is the purpose of Human-in-the-Loop (HITL) in the LangGraph agent?**  
*Answer:* Potentially destructive operations (such as converting production resource quantities or proposing imperative cluster actions) pause execution using LangGraph's `interrupt()` mechanism. Execution state is persisted in MemorySaver until an explicit human approval is received via `POST /agent/approve`, preventing accidental cluster misconfigurations.

**Q3: How does the CI/CD pipeline protect the main branch?**  
*Answer:* The GitHub Actions workflow (`.github/workflows/ci.yml`) runs bytecode syntax compilation (`compileall`), Ruff PEP 8 linting, and 154 pytest cases with coverage checks on all pull requests and feature branches. Production Docker images are only published to GHCR upon verified merges into the `main` branch.
