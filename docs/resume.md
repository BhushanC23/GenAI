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
   Engineered an end-to-end Kubernetes developer assistant indexing official Kubernetes docs via ChromaDB vector embeddings and TF-IDF search, returning answers with citations that link to the official Kubernetes page of each retrieved chunk, an honest "I don't know" for out-of-scope questions, and a Docker image published to GitHub Container Registry (GHCR) by CI.

2. **Engineered Agentic Workflow & Human-in-the-Loop Guardrails (LangGraph, ReAct):**  
   Implemented an autonomous multi-step reasoning agent using LangGraph with state persistence via MemorySaver and Human-in-the-Loop (HITL) approval interrupts, coupled with a deterministic quantity converter for CPU millicores and memory SI units, validated by 162 automated pytest tests with 75% coverage (Day 14 run).

3. **Implemented Automated CI/CD & Production Observability (GitHub Actions, Telemetry, Cache):**  
   Constructed an automated GitHub Actions CI/CD pipeline enforcing PEP 8 Ruff linting, Python bytecode validation, and Docker image builds published to GHCR, alongside request latency/token-estimate telemetry and an in-memory RAG query cache that serves repeated questions in well under 1 ms with no LLM call (measured on Day 14 with the mock provider: about 110 ms median on a cache miss vs about 0.01 ms on a hit).

---

## Technical Skills Matrix

| Domain | Technologies & Architectural Patterns |
|---|---|
| **GenAI & RAG** | Retrieval-Augmented Generation (RAG), ChromaDB Vector Store, Sentence Transformers (`all-MiniLM-L6-v2`), Sliding-Window Chunking, Cosine Similarity, Citations Grounding, Context Sufficiency Guardrails, Out-of-Scope Query Refusal |
| **Agentic AI & State** | LangGraph StateGraph, ReAct Loop, Human-in-the-Loop (HITL) Approval Interrupts, MemorySaver Checkpointing, Tool Calling, Deterministic Kubernetes Quantity Parsing (Millicores, Mi/Gi Binary and Decimal SI Units) |
| **Backend & APIs** | Python 3.11, FastAPI, Pydantic v2, Uvicorn, RESTful API Design, In-Memory Caching (LRU/FIFO), Latency Telemetry, Token Usage Accounting |
| **DevOps & Cloud** | Docker, Docker Compose, GitHub Actions CI/CD, GitHub Container Registry (GHCR); Render and Hugging Face Spaces deployments are configured but were not verified on Day 14 |
| **Quality Assurance** | Pytest, TestClient, Fixtures, Mocking, Boundary & Edge-Case Validation, Code Coverage (`pytest-cov`) |

---

## Production Telemetry & Cache Performance Metrics

> **Day 14 correction:** the Day 13 figures below are **estimates that cannot be reproduced from the repository** (no benchmark script is committed and the token counts are `characters // 4` estimates). Do not put them on a resume or quote them as measurements. Measured on Day 14 (mock LLM, local laptop, 10 questions): cache miss median about 110 ms, cache hit about 0.01 ms. See "Latency & Performance Telemetry" in `README.md`.

Day 13 estimates (kept for history) for the `/ask` endpoint under cold (cache miss) and warm (cache hit) loads:

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

**Q1: How does KubeCoach reduce hallucinations when answering Kubernetes questions?**  
*Answer:* It cannot guarantee zero hallucinations. It reduces them in two steps: first, ChromaDB retrieves the top-k chunks and the app checks that the best cosine similarity is at least 0.55; second, a sufficiency rule refuses when the question names an out-of-scope technology (a short list such as Istio or Terraform) or shares too few keywords with the retrieved text. A refused question returns "I don't know based on the provided official Kubernetes documentation" with no citations. With a real LLM the prompt also tells the model to answer only from the retrieved context. The rule is a heuristic and has known gaps (see "Known Limitations" in `README.md`).

**Q2: What is the purpose of Human-in-the-Loop (HITL) in the LangGraph agent?**  
*Answer:* The training task required a genuine pause/resume approval step before the `k8s_quantity_converter` tool runs. The agent graph calls LangGraph's `interrupt()`, the state is kept in `MemorySaver` (in memory, so it is lost on restart), and the run continues only after `POST /agent/approve` with `approved=true`. The converter itself is read-only arithmetic, so the gate demonstrates the pattern that would protect a real side-effecting tool.

**Q3: How does the CI/CD pipeline protect the main branch?**  
*Answer:* The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on pushes to `main` and `feature/**` and on pull requests to `main`. It runs bytecode syntax compilation (`compileall`), Ruff linting, the pytest suite with coverage, and a Docker build. The image is pushed to GHCR only on a push to `main`. The workflow does not by itself block merges: that needs a branch-protection rule in the GitHub repository settings, which was not verified.
