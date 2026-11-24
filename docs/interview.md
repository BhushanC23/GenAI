# KubeCoach: Interview Preparation (Day 14)

**Candidate:** Bhushan Kailas Chaturbhuj, MCA, Sanjivani University
**Project:** KubeCoach (SJ-58), Developer Tools: "Learn Kubernetes in Simple English"
**Repository:** https://github.com/BhushanC23/GenAI

Every technical statement in this file was checked against the code in this repository or against a command run during the Day 14 audit. Where something is *not* verified, the text says so. Read [section G](#g-what-i-must-be-able-to-explain-independently) before any interview.

Contents: [A. Pitch](#a-60-second-project-pitch) | [B. Hardest problem](#b-my-hardest-technical-problem) | [C. Ten questions](#c-ten-likely-interview-questions-and-answers) | [D. Architecture](#d-architecture-explanation) | [E. Tech stack](#e-technology-stack) | [F. Demo](#f-demo-preparation) | [G. Safety](#g-what-i-must-be-able-to-explain-independently)

---

## A. 60-Second Project Pitch

> KubeCoach is a learning assistant that explains Kubernetes in simple English. The official Kubernetes documentation is accurate but dense, so beginners, such as students preparing for DevOps interviews, find it hard to learn what an object does and which `kubectl` command to run.
>
> I built it as a RAG application, which means retrieval-augmented generation. I downloaded official Kubernetes concept pages, split them into small chunks, converted the chunks into embeddings with a sentence-transformers model, and stored them in ChromaDB. When a student asks a question in the Streamlit chat, my FastAPI backend finds the closest chunks, checks that they really relate to the question, and returns a plain-English answer with links to the official pages. If the documents do not cover the question, it says "I don't know" instead of guessing.
>
> I also added an agent built with LangGraph. It has a quantity converter, for example 500m CPU equals 0.5 cores, and it asks for approval before running.
>
> The project has 162 pytest tests, a Dockerfile, and a GitHub Actions pipeline. It is a small knowledge base of six documentation pages, so it is a learning project, not a replacement for the official docs.

*About 180 words, roughly 70 to 80 seconds at a calm pace. For a strict 60 seconds, drop the last paragraph or the agent paragraph. Practise it aloud once with a timer.*

**30-second version:** "KubeCoach explains Kubernetes in simple English. It searches official Kubernetes documentation stored in a ChromaDB vector database, then FastAPI returns a grounded answer with source links, and Streamlit is the chat interface. If the docs do not cover a question it says 'I don't know'. There is also a LangGraph agent with a CPU and memory converter that asks for approval first."

---

## B. My Hardest Technical Problem

**Chosen problem: making the answers trustworthy. That means refusing questions the documents cannot answer, and making sure every citation is a real documentation link.**

I chose this because the repository has evidence for each step: the rule in `app/rag.py`, the evaluation report `eval/rag_comparison.md`, the regression tests in `tests/test_day14.py`, and the Day 14 audit commands. I did not choose the Windows OpenMP story (see the note at the end) because I cannot reproduce it from the repository.

### STAR version (for a detailed answer)

**Situation.** A RAG chatbot can sound confident while being wrong. KubeCoach had to answer from official Kubernetes pages only, cite real pages, and say "I don't know" for an out-of-scope question. The training project set one such question as a test (Q6: "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?").

**Task.** Make the system refuse Q6 and similar questions without hard-coding the text of Q6, keep citations pointing to real URLs, and prove it with an evaluation set and tests.

**Action.**
1. *Measured instead of guessing.* Vector similarity alone did not work. In the Day 14 measurement, Q6 scored a top similarity of 0.74, higher than answerable questions such as Q5 (0.72) and Q10 (0.64). Any single threshold that refuses Q6 would also refuse good questions. So `is_context_sufficient()` in `app/rag.py` combines several signals: a minimum similarity (0.55), a short list of out-of-scope technology names (Istio, Terraform, Nomad, ...) that must also be missing from the retrieved text, and keyword coverage.
2. *Built an evaluation set.* `eval/eval_set.json` has 15 questions (Q6 is flagged unanswerable) and `eval/run_eval.py` compares two chunking configurations.
3. *Audited the running application on Day 14* instead of trusting the passing tests (the audit was done with an AI coding assistant, and I reviewed each change). The audit found three real faults that all 154 tests had missed:
   - The ChromaDB index on disk was built by an older version of the chunker. 417 of its 435 chunk IDs no longer matched what the code produces, and **citations to the raw pages showed `raw/pods.md` instead of the official URL**.
   - YAML frontmatter (`reviewers:`, `title:`, `weight:`) was embedded in chunks and appeared at the start of answers.
   - "What is the capital of France?" was *answered* from Namespaces text (similarity 0.59, and the keyword rule only applied to queries with three or more keywords).
4. *Fixed each cause and added tests.* `KubeCoachVectorStore.sync_chunks()` compares stored and expected chunk IDs and rebuilds only when they differ. `clean_markdown_for_chunking()` strips frontmatter. `is_context_sufficient()` refuses when no query keyword appears in the retrieved text. Eight regression tests in `tests/test_day14.py` cover these.

**Result.** After the fixes, in a live run of the API: citations for the Pods, Service, ConfigMap and Namespace questions were official `https://kubernetes.io/docs/concepts/...` URLs; Q6, the Terraform question and "capital of France" were refused with an empty citation list; the full suite shows 162 passed. `python -m eval.run_eval` completes, with Q6 refused correctly and 0 citations in both configurations.

**What is still not solved (say this too).** The refusal rule is a heuristic. Q6 is refused because of the out-of-scope term list, not because of the similarity threshold. A question whose words appear somewhere in the retrieved text, such as "What is a Horizontal Pod Autoscaler?", is treated as answerable. In offline (mock) mode the answer then shows the Pods introduction rather than an HPA definition, because HPA is not in the six indexed pages. The proper fix is a larger knowledge base plus a reranker, which I have not built.

### Short spoken version (about 45 seconds)

> My hardest problem was making the answers trustworthy. Similarity scores alone could not separate the out-of-scope Istio question from valid questions, because the Istio question scored higher than some answerable ones. So I combined a similarity threshold, a list of out-of-scope technologies, and keyword coverage, and I built a 15-question evaluation set. On the final audit I ran the real application and found problems that the tests missed: an old vector index gave citations like `raw/pods.md` instead of real URLs, frontmatter text leaked into answers, and an off-topic question was answered. I fixed all three and added regression tests. It is still a heuristic, and I know where it fails.

### Note on the other candidate story: the Windows OpenMP clash

`README.md` (Day 7) says that on Windows, `chroma-hnswlib` (MSVC OpenMP) and `scikit-learn` (LLVM OpenMP) conflicted, and that import order fixed it. The code does contain a related guard (`app/main.py` imports `hnswlib`, optionally, before other C-extension libraries, and the warm-up runs in the start-up hook). I did **not** reproduce the crash on Day 14, and newer ChromaDB no longer installs `hnswlib`. Use this story only if you remember the problem yourself and can explain it. If not, use the story above.

---

## C. Ten Likely Interview Questions and Answers

### 1. What is KubeCoach and why did you build it?

**Simple:** It is a chatbot that teaches Kubernetes in plain English and shows which official page each answer came from. I built it as my project for a 15-day Agentic AI training program (project SJ-58, theme Developer Tools).

**Technical:** A FastAPI backend does retrieval-augmented generation over 6 official Kubernetes concept pages plus 18 structured records (427 chunks in ChromaDB). A Streamlit UI calls it. A LangGraph agent adds a tool, `k8s_quantity_converter`. The target user is a student learning Kubernetes on Minikube who finds the official docs dense.

**Be ready to add:** it is a learning project with a small knowledge base.

### 2. Explain the complete architecture.

Request path for a question (see the diagram in section D):

1. The user types a question in Streamlit (`ui/app.py`). The UI never does RAG itself. It calls the backend through `ui/api_client.py` over HTTP (`POST /ask`, or `POST /agent` in Agent mode).
2. FastAPI (`app/main.py`) validates the request with Pydantic (question 3 to 1000 characters, `top_k` 1 to 20), then checks an in-memory cache.
3. On a miss, `execute_rag_pipeline()` in `app/rag.py` embeds the question, asks ChromaDB (`app/vectorstore.py`) for the `top_k` closest chunks, and runs the sufficiency check.
4. If the context is not sufficient, it returns "I don't know ..." with `citations: []`.
5. Otherwise it builds the answer. With a valid Groq or Gemini key it sends the chunks plus the question to the LLM (`app/llm.py`). Without a key it uses a built-in grounded mock that returns the first sentences of the best chunk.
6. Citations are built from the retrieved chunks' metadata (title, official URL, page, chunk ID). The JSON goes back to Streamlit, which shows the answer, source links, an object-relationship strip, and thumbs up/down feedback (`POST /feedback`).

### 3. What is RAG and why did you use it?

**Simple:** Instead of letting the AI answer from memory, you first look up the relevant documentation and give it to the AI together with the question. The AI then explains what is in the text.

**Technical:** RAG = retrieve + augment + generate. An LLM alone can invent `kubectl` flags and has a knowledge cutoff. Retrieval gives it current, checkable source text, lets me attach citations, and lets me refuse when nothing relevant is found. I preferred RAG over fine-tuning because the knowledge base is small, easy to update by re-indexing, and fine-tuning would not give me source links.

### 4. What are embeddings, and why is ChromaDB used?

**Simple:** An embedding turns a piece of text into a list of numbers so that texts with similar meaning get similar numbers. ChromaDB is a database that stores those numbers and can quickly find the closest ones to a question.

**Technical:** I use the `all-MiniLM-L6-v2` sentence-transformers model, which produces a 384-dimension vector per text (`app/embed.py`), normalised. ChromaDB (`chromadb.PersistentClient`, folder `data/chroma_db/`) stores each chunk with its vector and metadata, using cosine distance (the index is created with `"hnsw:space": "cosine"`, an approximate nearest-neighbour index). The code converts distance to a score with `similarity = 1 - distance/2`, which equals `(1 + cosine)/2`. So 0.5 means "unrelated" and my 0.55 threshold is a low bar by itself. ChromaDB was chosen because it is free, runs locally with no server, persists to disk, and supports metadata filters. I would not claim it is the best choice at large scale.

### 5. How do chunking and retrieval work?

- **Chunking** (`app/chunking.py`): clean the page (remove YAML frontmatter, Hugo shortcodes, HTML comments), then cut it into pieces of about 500 characters with 100 characters of overlap. Each cut prefers a paragraph break, then a sentence end, then a space, so sentences are not cut in the middle. Overlap keeps context across boundaries. Each chunk gets an ID like `pods-md-c001-<8 hex of a SHA-256 hash of the text>` and metadata (`source`, `source_url`, `page`, `title`, `category`).
- **Indexing:** `index_documents()` upserts chunks, so running it twice does not create duplicates. `sync_chunks()` compares stored IDs to the expected IDs and rebuilds only when they differ, because the ID contains a hash of the text.
- **Retrieval:** embed the question, get the top 3 nearest chunks (default `top_k=3`), convert distance to similarity.
- **Experiment I ran:** two configurations, 500/100 with k=3 and 800/150 with k=5, on 15 questions (`eval/rag_comparison.md`). On the Day 14 re-run they were effectively tied (retrieval relevance 86.7% both, answer keyword recall 32.2% vs 32.1%). The app uses the 500/100/3 defaults.

### 6. How do you reduce hallucinations and generate citations?

**Reducing hallucinations** (it reduces them, it does not eliminate them):
1. Answer only from retrieved chunks. The prompt in `prompts/rag_system_prompt.md` tells the LLM to use only the supplied context.
2. `is_context_sufficient()` refuses when (a) the best similarity is below 0.55, (b) the question names an out-of-scope technology from a short list and that word is absent from the retrieved text, (c) fewer than 25% of the keywords of a 3+ keyword question appear in the chunks, or (d) none of the keywords appear.
3. A refusal returns "I don't know based on the provided official Kubernetes documentation" with an empty `citations` list.
4. Temperature is low (`LLM_TEMPERATURE=0.2`).

**Citations:** `build_citations()` reads the metadata of the retrieved chunks (title, `source_url`, page, chunk ID) and removes duplicates. Nothing is typed by the model, so a citation cannot point to a page that was not retrieved.

**Honest limits:** every retrieved chunk is cited, even if the answer used only the first one (retrieval sources, not sentence-level attribution). The refusal rule is a heuristic with known gaps (section B).

### 7. Why did you use LangGraph or an agent workflow?

**Simple:** Plain RAG always does the same thing. An agent can choose between tools (search the docs, or convert a CPU or memory value) and can pause for a human to approve.

**Technical:** `app/graph.py` is a LangGraph `StateGraph` with four nodes: `reasoning_node` (choose a tool or finish), `approval_node`, `tool_execution_node`, and `final_response_node`. The state (`AgentState`) holds the question, messages, tool arguments, citations and an iteration counter (max 5). `k8s_rag_search` runs directly. For `k8s_quantity_converter` the graph calls `interrupt()`, which pauses and checkpoints the state in `MemorySaver`; the API returns `approval_required: true`, and `POST /agent/approve` resumes with `Command(resume={"approved": ...})`. Tools are on an allow-list and their arguments are validated (`app/tools.py`). The converter uses Python `Decimal`, never the LLM, for the arithmetic (`500m = 0.5` cores; `Mi`/`Gi` are powers of 1024; `M`/`G` are powers of 1000).

**Honest points:** the converter is read-only maths, so the approval step is there to show the pattern the training task required. Without an API key, tool choice comes from a deterministic rule-based planner (`_deterministic_mock_planner`), not an LLM. `MemorySaver` is in memory only. A hand-written ReAct loop (`app/agent_loop.py`) came first, and LangGraph was added for the state and interrupt features.

### 8. How do the FastAPI endpoints work with Streamlit?

FastAPI is the only place with logic. Streamlit is a thin client. Main endpoints (all visible at `/docs`): `GET /health`, `GET /records`, `GET /search` (TF-IDF), `GET /search/semantic` (ChromaDB), `POST /ask` (RAG), `POST /agent` and `POST /agent/approve`, `POST /feedback`, `GET /feedback`, `POST /chat`, `POST /questions`, `GET /cache/stats`, `POST /cache/clear`. Pydantic models validate input and return 422 for bad input; `/agent/approve` returns 409 when there is nothing to approve; LLM problems map to 429, 502, 503 or 504. `ui/api_client.py` wraps each call with timeouts (4 s health check, 30 s requests) and turns errors into messages. The UI keeps the chat in `st.session_state`. The backend address comes from the `API_BASE_URL` environment variable (default `http://127.0.0.1:8000`).

### 9. How did you test, evaluate and containerize the application?

- **Tests:** 162 pytest tests (`tests/`), 75% line coverage on `app/` and `ui/` (lowest: `app/llm.py` 55% and `ui/app.py` 51%, because live LLM calls are not tested). They include API tests with FastAPI's `TestClient`, unit tests for the converter's edge cases (zero, negative, bad suffix), agent interrupt/resume tests, a headless Streamlit `AppTest`, and the Day 14 regression tests. No test needs an LLM API key. A few load the real embedding model, which downloads on first use.
- **Evaluation:** `python -m eval.run_eval` runs 15 questions and reports retrieval relevance, citation correctness, keyword-recall answer score, Q6 refusal and latency. The metrics are simple: "citation correctness" only checks that citations exist with a title and URL.
- **Docker:** `Dockerfile` uses `python:3.11-slim`, installs CPU-only PyTorch first to keep the image smaller, copies the code, runs as a non-root user (`kubecoach`, UID 1000), exposes 8000 and 8501, has a `curl /health` health check, and starts through `docker-entrypoint.sh` (modes `api`, `ui`, `all`, `test`). `docker-compose.yml` runs backend and frontend with a named volume for `/app/data`. It is a single-stage build, not multi-stage.
- **CI:** `.github/workflows/ci.yml` runs `compileall`, `ruff check .`, `pytest --cov`, a Docker build, and (only on pushes to `main`) pushes the image to GHCR. The latest run I verified on `main` (run #8, commit `7b4b5ce`) succeeded, and the GHCR package exists.
- **Not verified on Day 14:** a local `docker run` (see `PROGRESS.md`).

### 10. What was your biggest challenge, what are the limitations, and what would you improve next?

**Biggest challenge:** trustworthy answers (section B).

**Limitations (say them before the interviewer finds them):**
- Only 6 documentation pages and 18 short records are indexed.
- The refusal rule is a heuristic with a hard-coded list of out-of-scope technologies.
- Citations are per retrieved chunk, not per sentence.
- Without an LLM key, answers are extractive snippets and may miss the exact `kubectl` command asked for.
- I did not test the live Groq or Gemini path on Day 14.
- No authentication or rate limiting. The cache and agent sessions are in memory only.
- The README's older performance numbers (for example "1,420 ms cold") are estimates, not measurements. Measured with the mock LLM: median 110 ms on a cache miss, 0.01 ms on a hit.

**Next improvements:** index more pages (HPA, StatefulSet, Jobs, storage); add a reranker and sentence-level citations; bake the embedding model into the image; add authentication and rate limiting; separate the GHCR publish step so `packages: write` is not granted to the test job; add a human-reviewed answer-quality set.

---

## D. Architecture Explanation

```text
Student (browser)
   |
   v
Streamlit UI  (ui/app.py, port 8501)
   |   HTTP via ui/api_client.py  (API_BASE_URL, timeouts, error messages)
   v
FastAPI backend  (app/main.py, port 8000)  -- Pydantic validation, error codes, /docs
   |
   +--> GET /search ............ TF-IDF + cosine over records.json   (app/smart_search.py)
   |
   +--> GET /search/semantic ... embeddings + ChromaDB                (app/vectorstore.py)
   |
   +--> POST /ask  (RAG)
   |       |
   |       +--> in-memory cache hit? -> return cached answer
   |       |
   |       +--> embed question (all-MiniLM-L6-v2, app/embed.py)
   |       +--> ChromaDB top-k chunks (data/chroma_db, cosine)
   |       +--> is_context_sufficient()  (app/rag.py)
   |               |-- no  -> "I don't know ..." + citations: []
   |               '-- yes -> LLM (Groq / Gemini)  or  grounded mock (no API key)
   |                          -> answer + citations built from chunk metadata
   |
   +--> POST /agent, /agent/approve  (LangGraph, app/graph.py)
   |       reasoning_node -> (k8s_rag_search) -> tool_execution_node -> reasoning_node -> final_response_node
   |                    \-> (k8s_quantity_converter) -> approval_node [interrupt, MemorySaver]
   |                                                        approved -> tool_execution_node
   |                                                        rejected -> final_response_node
   |
   '--> POST /feedback -> data/feedback.json

Knowledge base build (offline, once):
   data/raw/*.md (6 official pages) + data/records.json (18 records)
      -> clean + chunk (500 chars, overlap 100) -> embed -> upsert into ChromaDB (427 chunks)

Answer + citations (official kubernetes.io URLs) -> FastAPI JSON -> Streamlit (answer, links, relationship strip, feedback)
```

---

## E. Technology Stack

Only technologies present in `requirements.txt`, the Dockerfile, or the workflow are listed.

| Technology | Responsibility in KubeCoach |
|---|---|
| Python 3.11 | Language for all backend, agent, evaluation and UI code. |
| FastAPI + Uvicorn | REST API (`app/main.py`), automatic `/docs` page, ASGI server. |
| Pydantic v2 | Request and response validation (lengths, ranges, types). |
| Streamlit | Chat UI (`ui/app.py`): RAG and Agent modes, citations, feedback, approval buttons. |
| `requests` | Streamlit client calls to the API; downloading Kubernetes pages (`app/fetch.py`). |
| sentence-transformers (`all-MiniLM-L6-v2`) | Turns chunks and questions into 384-dimension embeddings. |
| ChromaDB | Persistent vector database with cosine nearest-neighbour search. |
| scikit-learn, pandas, numpy | TF-IDF keyword search (`/search`) and the Day 4 data analysis. |
| Groq SDK, `httpx` (Gemini REST) | Optional live LLM providers, chosen by `LLM_PROVIDER` and API keys in `.env`. |
| python-dotenv | Loads environment variables from `.env` (never committed). |
| LangGraph | Agent state graph, `MemorySaver` memory, `interrupt()` human approval. |
| pytest, pytest-cov | 162 tests and coverage. |
| Ruff | Lint check (`ruff.toml`, rules E, F, W). |
| Docker, Docker Compose | Container image (non-root, health check) and backend + frontend orchestration. |
| GitHub Actions, GHCR | CI pipeline and Docker image publishing from `main`. |
| Render (`render.yaml`) | Deployment blueprint. The live deployment was **not** verified on Day 14. |

---

## F. Demo Preparation

Run from the `GenAI` folder (Windows PowerShell). Python 3.11 is required (`.venv311` is the Python 3.11 environment on this machine). Do a full dry run the day before.

1. **Start the API** (terminal 1):
   ```powershell
   .\.venv311\Scripts\Activate.ps1
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   Wait for "Application startup complete". On the very first start it downloads the embedding model and builds the index (internet needed).
2. **Start the UI** (terminal 2): `streamlit run ui/app.py`, then open http://127.0.0.1:8501. The sidebar should show the backend as Online.
3. **Ask a question** in RAG mode: `What is a Pod and what command lists running pods?`
4. **Explain the answer:** it is extractive when no LLM key is set. Say so. With a Groq or Gemini key in `.env` the wording is generated from the same chunks.
5. **Show citations:** click the source link. It opens the official `kubernetes.io/docs/concepts/workloads/pods/` page.
6. **Show the refusal:** ask `How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?` Expected: "I don't know ..." with no citations and no relationship strip. Then `What is the capital of France?` shows the same.
7. **Show the agent:** switch to Agent mode and type `Convert 500m CPU to cores`. The UI shows an approval card. Click Approve and the result is `0.5 cores`. Try `Compare 1Gi and 1G memory` and reject it to show the tool is skipped.
8. **Show the API docs:** http://127.0.0.1:8000/docs. Run `POST /ask` and `GET /search/semantic?q=pod is crashing repeatedly`. Optionally show `GET /cache/stats` after asking the same question twice (the second answer has `cached: true`).
9. **Explain Docker:**
   ```powershell
   docker build -t kubecoach .
   docker run -d --name kubecoach-container -p 8000:8000 -v kubecoach_data:/app/data kubecoach
   docker compose up -d      # backend :8000 and Streamlit :8501
   ```
   Say that the image is non-root, has a health check, and uses `LLM_PROVIDER=mock` by default. **Day 14 caveat:** I could not run the container locally (Docker Desktop stopped when the disk filled up). Run it yourself before the demo, or show the image that CI published.
10. **Explain CI/CD:** open https://github.com/BhushanC23/GenAI/actions and show a green run of "CI Pipeline" (verified: run #8 on `main`, https://github.com/BhushanC23/GenAI/actions/runs/45056903970). Walk through the steps: checkout, Python 3.11, install, `compileall`, `ruff`, `pytest`, Docker build, GHCR login and push.

**Offline backup plan:** the real embedding model must already be cached on the machine (it is downloaded from Hugging Face on first use), so start the API once while online before the interview. Do not use `KUBECOACH_MOCK_EMBEDDINGS=1` for a demo: that switch is for tests, and its fake vectors give meaningless search results.

---

## G. What I Must Be Able to Explain Independently

Do not claim ownership of a topic until you can explain it without these notes. For each item, open the file named and read the function once.

| Topic | You should be able to explain | Where to look |
|---|---|---|
| **Python application flow** | What happens from `uvicorn app.main:app` to a JSON response; what the start-up hook does; how modules import each other. | `app/main.py` |
| **FastAPI endpoints** | What a route, a Pydantic model and a status code are; why bad input gives 422; what `/docs` is. | `app/main.py` |
| **RAG pipeline** | The 6 steps in Q2; why the sufficiency check exists; what is returned when it fails. | `app/rag.py::execute_rag_pipeline` |
| **Embeddings** | What a vector is; why similar meaning gives close vectors; what 384 dimensions and cosine similarity mean; what `(1 + cosine)/2` does to the score. | `app/embed.py`, `app/vectorstore.py::query_similar` |
| **ChromaDB** | What a collection, upsert and persistent client are; why IDs contain a hash; what `sync_chunks()` fixes. | `app/vectorstore.py` |
| **Chunking** | Why overlap is used; how the 500/100 split picks a boundary; what metadata is kept. | `app/chunking.py::split_text` |
| **LangGraph** | State, node, conditional edge, checkpointer, `interrupt()` and `Command(resume=...)`. | `app/graph.py` |
| **Agent tools** | Why the tool list is an allow-list; why maths is done in `Decimal`, not by the LLM; what the mock planner does. | `app/tools.py`, `app/agent_loop.py` |
| **Docker** | Image vs container, layers, why `requirements.txt` is copied first, what the non-root user and `HEALTHCHECK` do, what the volume stores. | `Dockerfile`, `docker-compose.yml` |
| **GitHub Actions** | Trigger, job, step, runner, permissions, why GHCR push is limited to `main`. | `.github/workflows/ci.yml`, `docs/ci_cd.md` |
| **Testing** | Unit vs integration test, `TestClient`, mocking, what 75% coverage does and does not prove. | `tests/`, `docs/testing.md` |

**Be honest about how the project was built.** The project was built with AI coding assistants as part of a training program. A good answer is: "I used AI tools to write and review code, and I can explain the flow of each module, the design choices, the tests, and the known weaknesses. The part I understand best is ..." Choose one area from the table, study it until you can explain it at the whiteboard, and lead with that.

**Do not say:**
- "It never hallucinates" or "100% accurate citations". Say it reduces hallucinations and cites the retrieved sources.
- "It is deployed and live" unless you opened the Render and Hugging Face links yourself that day (not verified on Day 14).
- Any latency, cost or "373x faster" figure from the old README. Only the Day 14 measured numbers (110 ms miss, 0.01 ms hit, mock LLM) are real.
- "Multi-stage Docker build". It is a single-stage Dockerfile.
- "Production-grade". There is no authentication, no rate limiting, and the agent memory is in RAM.

**Questions to expect that are not in the ten:** "What is the difference between TF-IDF and embeddings search?" (keyword match versus meaning match; both are in the app). "Why `top_k=3`?" (small context, fast; I compared k=3 and k=5 and they tied). "What happens if the LLM API is down?" (explicit 429/502/503/504 mapping in `/ask`; with no key the app falls back to the mock). "What would break if two users use the agent at once?" (sessions are separated by `session_id`, but memory is in one process and lost on restart).
