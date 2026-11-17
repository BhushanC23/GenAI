# KubeCoach

### Project ID: SJ-58
### Theme: Developer Tools
### Student: Bhushan Kailas Chaturbhuj (Reg. No: 2125PCAM1038)

## About
KubeCoach is an AI-powered educational developer learning tool designed to explain Kubernetes concepts and kubectl commands in simple English using official Kubernetes documentation.

## Target Users
Final-year IT students preparing for DevOps interviews and beginners practicing Kubernetes workloads on Minikube or local clusters.

## Problem
Official Kubernetes documentation is extensive and technically dense. Beginners often struggle to understand what each object does, which kubectl command to run, and how defaults are configured. KubeCoach provides structured, documentation-grounded explanations with smart search and interactive APIs.

## Data Source
- Official Documentation Concepts: https://kubernetes.io/docs/concepts/
- Official Documentation Source Repository: https://github.com/kubernetes/website

---

## Day 1 Progress — Python Foundations
- Created `day01_intro.py` introducing the project and student interactions.
- Created `day01_menu.py` with an interactive while-loop menu.
- Practised Python variables, data types, input, f-strings, conditional branching, and loop control.

## Day 2 Progress — Collections & Modular Architecture
- Added 18 structured Kubernetes records based on official documentation.
- Implemented list and dictionary data handling.
- Implemented keyword search and category counting.
- Organised reusable functions in `app/records.py`.
- Established a modular `app/` and `data/` project structure.
- Built an interactive terminal CLI (`app/cli.py`) for querying Kubernetes records.

## Day 3 Progress — Data Ingestion, Models & HTTP
- **Dataclass & OOP Modeling (`app/models.py`):**
  - Implemented the `Record` `@dataclass` representing standard knowledge records (`page_title`, `category`, `one_line_definition`, `key_kubectl_command`, `limit_or_default`, `source_url`, and `id`).
  - Added strict data validation and automated slug generation in `__post_init__`.
  - Defined custom error hierarchy: `KubeCoachError`, `ValidationError`, and `DataIngestionError`.
  - Implemented `to_dict()` and `from_dict()` serialization helpers.
- **HTTP Documentation Fetcher (`app/fetch.py`):**
  - Downloaded raw Markdown documentation pages from the official Kubernetes website repository.
  - Used `requests` with explicit timeouts and `raise_for_status()` validation.
  - Implemented structured error handling using `try...except...else...finally`.
  - Saved raw documentation to `data/raw/` along with `manifest.json` for data provenance.
- **Data Ingestion Pipeline (`app/ingest.py`):**
  - Parsed Markdown documents, extracting top-level YAML frontmatter and overview sections.
  - Stripped Hugo-specific shortcodes (`{{< glossary_tooltip >}}`), HTML comments, and formatting markers without data destruction.
  - Validated records against `Record` models and captured errors without crashing the pipeline.
  - Normalized and exported clean records to standard `data/records.json`.
- **Record Loading Refactor (`app/records.py`):**
  - Updated `load_records()` to load from `data/records.json` with a safe fallback to seed records.
  - Added `load_record_models()` returning validated `Record` dataclass instances.
  - Preserved backward compatibility for search, counting, and ID lookup without breaking the Day 2 CLI.
- **Automated Test Suite (`tests/test_day03.py`):**
  - 16 comprehensive unit tests covering models, validation, mock network failures, text cleaning, ingestion, and query functions.

## Day 4 Progress — FastAPI, Pandas Analysis & TF-IDF Smart Search
- **FastAPI REST Backend (`app/main.py`):**
  - Created high-performance RESTful API using FastAPI and Uvicorn.
  - Implemented Pydantic models (`QuestionRequest`, `QuestionResponse`, `HealthResponse`) for strict request and response validation.
  - Exposes 5 required endpoints with proper HTTP status codes (200, 201, 404, 422).
  - Persists student questions safely into `data/questions.json`.
  - Auto-generated interactive Swagger UI documentation at `/docs`.
- **Pandas Exploratory Data Analysis (`analysis/explore.py`):**
  - Loaded `data/records.json` into a Pandas DataFrame using `read_json()`.
  - Inspected dataset shape (18 rows, 7 columns), types (`info()`), first records (`head()`), and length metrics (`describe()`).
  - Grouped and counted records across categories using `value_counts()` and `groupby()`.
  - Derived 3 key observations regarding workload dominance (38.9%), domain diversity (6 categories), and 100% practical kubectl grounding.
- **TF-IDF & Cosine Similarity Smart Search (`app/smart_search.py`):**
  - Engineered a searchable text corpus combining record identifiers, titles, categories, definitions, kubectl commands, and configuration limits.
  - Utilized scikit-learn's `TfidfVectorizer` (with English stop words and sublinear TF scaling) to vectorize queries and documents.
  - Calculated pairwise `cosine_similarity` to rank records by relevance.
  - Returns top 3 ranked records with relevance scores rounded to 4 decimals.
  - Integrated smart search into the `GET /search?q=` API endpoint.
- **Comprehensive Test Suite (`tests/test_day04.py`):**
  - 18 automated unit tests using `fastapi.testclient.TestClient` covering endpoint contracts, query parameters, 404 handling, Pydantic validation, and question persistence. Total test suite now runs 34 passing tests.

## Day 5 Progress — Deep Learning and LLM Fundamentals
- **Comprehensive LLM Technical Guide ([`docs/how_llms_work.md`](docs/how_llms_work.md)):**
  - Documented the AI hierarchy (Artificial Intelligence vs. Machine Learning vs. Deep Learning) and why deep neural representations outperform brittle rule-based expert systems for technical language.
  - Explained tokenization (Byte-Pair Encoding), vector embeddings (semantic coordinate spaces), and the Transformer architecture with self-attention ($Q, K, V$ mechanics).
  - Walked through autoregressive next-token prediction and the three training stages: Pre-training, Instruction Fine-Tuning (SFT), and Reinforcement Learning from Human Feedback (RLHF).
  - Analyzed critical DevOps limitations of LLMs: hallucinations (fabricating invalid `kubectl` flags), finite context windows, knowledge cutoff, and per-token compute costs.
  - Added a visual Mermaid architecture diagram illustrating the end-to-end LLM inference lifecycle.
- **Evaluation Benchmark Dataset ([`eval/questions.json`](eval/questions.json)):**
  - Formulated a 10-question evaluation benchmark spanning container workloads, networking, configuration, storage, and cluster administration.
  - Included 6 core questions from the official project card plus 4 realistic beginner DevOps queries.
  - Marked question **Q6** (*"How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?"*) as `unanswerable: true`.
  - **Why Q6 is Unanswerable:** KubeCoach's current knowledge base is grounded strictly in the 18 core Kubernetes concepts from official documentation. Istio and third-party service meshes represent an external domain outside this core knowledge base; marking Q6 unanswerable establishes an honesty benchmark so future RAG systems safely refuse out-of-scope queries rather than hallucinating answers.
- **Checkpoint 1 Evaluation Guide ([`docs/checkpoint_1.md`](docs/checkpoint_1.md)):**
  - Prepared step-by-step instructions for running the FastAPI application, demonstrating Swagger UI at `/docs`, and answering viva questions.
  - Included a beginner-friendly, line-by-line breakdown of `smart_search()` in `app/smart_search.py` covering inputs, corpus generation, TF-IDF vectorization, Cosine Similarity math, and top-3 ranking.

## Day 6 Progress — LLM Integration & Prompt Engineering
- **Unified LLM Provider Wrapper ([`app/llm.py`](app/llm.py)):**
  - Architected a multi-provider LLM client supporting **Groq** (`groq.Groq` SDK) and **Google Gemini** (direct HTTP REST via `httpx` to ensure broad Python compatibility).
  - Built an offline **Grounded Mock Provider** backed by the local 18-record knowledge base and TF-IDF search so development, CI/CD, and offline testing operate with zero external API key requirements.
  - Implemented resilient error handling with custom exceptions: `LLMConfigurationError`, `LLMAuthenticationError`, `LLMRateLimitError`, `LLMTimeoutError`, and `LLMProviderError`.
  - Added robust structured JSON response parsing with regex fallback to extract `answer`, `confidence`, and `follow_up` fields even when providers wrap output in Markdown code blocks or return conversational preambles.
- **Interactive Chat Endpoint (`POST /chat` in [`app/main.py`](app/main.py)):**
  - Added `ChatRequest` (validating `query` between 3 and 1,000 characters) and `ChatResponse` (`answer`, `confidence`, `follow_up`, `provider`, `model`, `grounded_records`).
  - Integrated provider-agnostic inference returning structured JSON.
  - Mapped LLM error conditions to explicit HTTP status codes: `429 Too Many Requests`, `502 Bad Gateway`, `503 Service Unavailable`, and `504 Gateway Timeout`.
  - Preserved 100% backward compatibility with all Day 4 endpoints (`/`, `/health`, `/records`, `/records/{id}`, `/search`, `/questions`).
- **Prompt Engineering Library (`prompts/`):**
  - **Master System Prompt ([`prompts/system_prompt.md`](prompts/system_prompt.md)):** Establishes KubeCoach persona, target audience of final-year students, educational clarity, strict zero-hallucination policy (admitting unknowns rather than fabricating), and structured JSON output schema.
  - **Concept Explanation Template ([`prompts/explain_concept.md`](prompts/explain_concept.md)):** 5-part educational framework: 1-sentence definition, "Why it exists", real-world analogy, primary `kubectl` command, and default limits.
  - **Kubectl Command Helper ([`prompts/kubectl_helper.md`](prompts/kubectl_helper.md)):** Practical operator prompt providing command syntax, breakdown of critical flags, safety warnings (`--force`, `--grace-period=0`), and verification commands.
- **Systematic Prompt Evaluation ([`eval/prompt_compare.md`](eval/prompt_compare.md)):**
  - Conducted a side-by-side benchmark comparing **Prompt A (Baseline/Generic)** vs. **Prompt B (Structured/Grounded KubeCoach)** across all 10 questions in `eval/questions.json`.
  - Scored both variants across Groundedness (1–5), Beginner Clarity (1–5), Actionable kubectl (1–5), and Format Compliance (1–5).
  - Confirmed that Prompt B scored **19.8 / 20** average vs. **10.9 / 20** for Prompt A, completely eliminating hallucination on question **Q6** (Istio mTLS) through grounded honest refusal.
- **Environment & Security Management:**
  - Created [`.env.example`](.env.example) with placeholder keys (`LLM_PROVIDER`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `LLM_MODEL`, hyperparameters).
  - Configured [`.gitignore`](.gitignore) so actual `.env` files with secret API keys are never committed to version control.
- **Comprehensive Test Suite ([`tests/test_day06.py`](tests/test_day06.py)):**
  - Added 13 automated unit tests covering provider initialization, structured JSON parsing, mock responses, prompt file existence, `/chat` endpoint status codes, validation errors, and endpoint regression tests. Total test suite now runs **47 passing tests**.

## Day 7 Progress — Dense Embeddings & ChromaDB Semantic Search
- **Document Chunking Engine ([`app/chunking.py`](app/chunking.py)):**
  - Developed a specialized documentation chunker for Kubernetes Markdown concepts and JSON records.
  - Configurable sliding-window token/word chunking (`chunk_size=400`, `chunk_overlap=80` words) ensuring semantic continuity across chunk boundaries.
  - Cleans raw Hugo shortcodes (`{{< ... >}}`), HTML comments, and formatting markers while preserving code blocks and command explanations.
  - Generates deterministic, traceable chunk IDs (`doc:pod:chunk:001`, `record:pod:chunk:001`) with rich metadata preservation (`source`, `page`, `title`, `category`, `h2_section`).
  - Chunks the entire knowledge base (18 structured records + 6 raw official Kubernetes concept documents: `pods.md`, `deployment.md`, `service.md`, `ingress.md`, `configmap.md`, `namespaces.md`) into **435 indexed chunks**.
- **Dense Vector Embeddings ([`app/embed.py`](app/embed.py)):**
  - Integrated `sentence-transformers` utilizing the pretrained `all-MiniLM-L6-v2` bi-encoder model, mapping text to dense 384-dimensional vector space ($\mathbb{R}^{384}$).
  - Built a lazy-loaded singleton embedding manager (`EmbeddingProvider`) supporting high-throughput batch encoding (`embed_texts`) and single-query encoding (`embed_query`).
  - Implemented an offline deterministic `MockEmbeddingProvider` utilizing SHA-256 seed hashing to produce normalized 384-dimensional vectors for lightning-fast, zero-network unit testing and CI/CD pipelines.
- **Persistent ChromaDB Vector Store ([`app/vectorstore.py`](app/vectorstore.py)):**
  - Implemented local persistent vector storage via `chromadb.PersistentClient` rooted in `data/chroma_db/`.
  - Configured collection metadata with Cosine space (`hnsw:space="cosine"`) and atomic disk synchronization (`hnsw:sync_threshold=50`) guaranteeing complete HNSW index file persistence across process restarts.
  - Built idempotent batch upsert (`add_chunks`) with automatic deduplication preventing duplicate vector entries on repeated ingest runs.
  - Implemented `query_similar` supporting top-$k$ nearest neighbor retrieval, metadata filtering (`category`, `source`), and cosine distance to similarity score conversion: $\text{similarity} = 1.0 - (\text{cosine\_distance} / 2.0)$.
- **Semantic Search API Endpoint (`GET /search/semantic` in [`app/main.py`](app/main.py)):**
  - Added REST endpoint `GET /search/semantic?q={query}&limit={limit}&category={category}` returning validated `SemanticSearchResponse` with list of `SemanticSearchResult` objects.
  - Resolved low-level Windows OpenMP runtime collision between MSVC OpenMP (`vcomp140.dll` used by `chroma-hnswlib`) and LLVM OpenMP (`libomp140.x86_64.dll` used by `scikit-learn`) through top-level initialization and lazy module loading.
  - Validates queries ($3 \le \text{length} \le 500$), validates limit ($1 \le \text{limit} \le 20$), and supports optional category filtering.
- **Systematic Evaluation Benchmark ([`eval/search_results.md`](eval/search_results.md)):**
  - Ran all 10 benchmark questions from `eval/questions.json` through both **Semantic Search (Dense MiniLM + ChromaDB)** and **Smart Search (Sparse TF-IDF + Cosine Similarity)**.
  - Recorded genuine scores, top retrieved chunks, and qualitative behavioral comparisons:
    - **Semantic Search Strengths:** Understands synonyms, conceptual phrasing, and conversational queries (e.g., Q1 "crashloopbackoff" surfaces troubleshooting chunks, Q3 "exposing deployment externally" surfaces Ingress/Service routing concepts, Q8 "config and sensitive data" correctly links to ConfigMap and Secret boundaries).
    - **TF-IDF Search Strengths:** Superior for exact lexical keyword lookups and literal command flags (e.g., exact `kubectl port-forward` string matching).
    - **Out-of-Scope Detection (Q6 Istio mTLS):** Semantic search returned low similarity scores against core concepts, providing the mathematical grounding threshold necessary for Day 8 RAG hallucination guardrails.
- **Semantic Search Architecture Flow:**
  ```mermaid
  flowchart TD
    A["Official Documentation<br/>(data/raw/*.md, data/records.json)"] --> B["Document Chunking Engine<br/>(app/chunking.py)<br/>chunk_size=400, overlap=80"]
    B --> C["435 Document Chunks<br/>(Text + Metadata + Stable IDs)"]
    C --> D["Dense Vector Embeddings<br/>(app/embed.py)<br/>all-MiniLM-L6-v2 (384 dims)"]
    D --> E["Persistent ChromaDB Store<br/>(data/chroma_db)<br/>HNSW Cosine Index"]
    F["User Query<br/>(GET /search/semantic?q=...)"] --> G["Query Embedding<br/>(app/embed.py)"]
    G --> H["k-NN Similarity Search<br/>(app/vectorstore.py)"]
    E --> H
    H --> I["Ranked Top Chunks<br/>(Cosine Similarity + Metadata)"]
  ```
- **Comprehensive Test Suite ([`tests/test_day07.py`](tests/test_day07.py)):**
  - Added 16 automated unit tests validating chunk size boundaries, sliding overlap, metadata preservation, embedding dimensions and normalization, ChromaDB persistent deduplication, category filtering, and FastAPI endpoint response contracts.
  - Project test suite now totals **63 passing unit tests** across Days 3, 4, 6, and 7.

## Day 8 Progress — Grounded RAG with Citations & Multi-Config Evaluation
- **End-to-End Grounded RAG Pipeline ([`app/rag.py`](app/rag.py)):**
  - Architected a modular Retrieval-Augmented Generation (RAG) engine connecting vector retrieval to structured LLM inference.
  - Converts user questions into 384-dimensional dense vectors using `all-MiniLM-L6-v2` (`app/embed.py`).
  - Retrieves top-$k$ nearest neighbor document chunks from persistent ChromaDB collections (`data/chroma_db`).
  - Implements a **generalized context sufficiency and domain coverage rule** (`is_context_sufficient`):
    - Evaluates semantic similarity thresholds ($S \ge 0.55$) and query entity coverage across retrieved text.
    - Out-of-scope technologies (e.g. Istio Service Mesh, Nomad, Linkerd) are detected mathematically rather than hardcoded.
    - Questions lacking sufficient context receive an honest refusal: *"I don't know based on the provided official Kubernetes documentation."* with exactly **0 fake citations**.
  - Formats retrieved chunks into numbered context blocks (`[Context Block 1]`) with document titles, source URLs, and file paths.
  - Supports live inference via **Groq** and **Google Gemini**, with automatic fallback to a local grounded mock generator for offline development and testing.
- **Verifiable Citation Engine:**
  - Extracts and deduplicates structured citations based strictly on retrieved chunks used during answer generation.
  - Each citation provides `document_title`, `source_url` (grounded in official `kubernetes.io/docs/concepts/` URLs), and `page` source file.
  - Guarantees zero fabricated citations: if the system refuses with "I don't know", the citation list is strictly empty (`[]`).
- **Interactive RAG API Endpoint (`POST /ask` in [`app/main.py`](app/main.py)):**
  - Exposes `POST /ask` accepting `AskRequest` (`question: str`, optional `top_k: int = 3`).
  - Returns validated `AskResponse` containing `answer`, `citations`, `retrieved_chunks`, `confidence`, and `context_sufficient`.
  - Comprehensive HTTP error handling: `422 Unprocessable` for invalid inputs, `503 Unavailable` for vector store failures, `429 Too Many Requests` for rate limits, `504 Gateway Timeout` for slow provider requests, and `502 Bad Gateway` for provider errors.
  - Fully backward compatible: all previous Day 1–7 endpoints (`/`, `/health`, `/records`, `/search`, `/search/semantic`, `/questions`, `/chat`) remain operational.
- **RAG Architecture & Workflow:**
  ```mermaid
  flowchart TD
    A["User Question<br/>(POST /ask)"] --> B["Dense Embedding<br/>(app/embed.py)<br/>all-MiniLM-L6-v2"]
    B --> C["ChromaDB Vector Store<br/>(app/vectorstore.py)<br/>Top-k Cosine Retrieval"]
    C --> D{"Context Sufficiency<br/>Check (app/rag.py)"}
    D -- "Insufficient / Out-of-Scope<br/>(e.g. Q6 Istio mTLS)" --> E["Honest Refusal<br/>'I don't know...'<br/>Citations: []"]
    D -- "Sufficient Context" --> F["Grounded Prompt Builder<br/>Numbered Context Blocks<br/>+ System Directives"]
    F --> G["LLM Provider Wrapper<br/>(Groq / Gemini / Mock)"]
    G --> H["Grounded Explanation<br/>+ kubectl Commands<br/>+ Verified Citations"]
  ```
- **15-Question Evaluation Dataset ([`eval/eval_set.json`](eval/eval_set.json)):**
  - Formulated a comprehensive benchmark dataset preserving all 10 existing questions from `eval/questions.json` (including out-of-scope question **Q6** with `is_answerable: false`).
  - Added 5 new official documentation grounded questions:
    - `Q11`: Pod `restartPolicy` allowed values and default (`Always`).
    - `Q12`: Differences between `ClusterIP` and `NodePort` Services.
    - `Q13`: Deployment rolling update mechanics and ReplicaSet transitions.
    - `Q14`: Ingress controller requirements beyond Ingress resource rules.
    - `Q15`: Differences between `PersistentVolume` (PV) and `PersistentVolumeClaim` (PVC).
- **RAG Configuration Benchmark ([`eval/run_eval.py`](eval/run_eval.py) & [`eval/rag_comparison.md`](eval/rag_comparison.md)):**
  - Evaluated and compared two distinct architectural configurations across all 15 questions:
    - **Configuration A:** Chunk size 500 chars, overlap 100 chars, top-$k=3$ (435 chunks indexed).
    - **Configuration B:** Chunk size 800 chars, overlap 150 chars, top-$k=5$ (275 chunks indexed).
  - Benchmark Summary:

    | Metric | Configuration A (500 chars, k=3) | Configuration B (800 chars, k=5) | Winning Config |
    | :--- | :--- | :--- | :--- |
    | **Total Chunks in Collection** | 435 chunks | 275 chunks | Config A (Finer granularity) |
    | **Retrieval Relevance** | **86.7%** | **86.7%** | **Tie** |
    | **Citation Correctness** | **93.3%** | **100.0%** | **Configuration B** |
    | **Answer Correctness (Recall)** | **32.6%** | **32.0%** | **Configuration A** |
    | **Q6 Refusal ('I don't know')** | **PASS (100%)** | **PASS (100%)** | **Tie (Both Pass)** |
    | **Average Latency per Query** | **29.6 ms** | **24.6 ms** | **Configuration B** |
    | **Overall Benchmark Winner** | - | **Configuration B** | Higher citation coverage & speed |

  - **Winning Configuration Rationale:** **Configuration B** achieved higher aggregate score by providing 100.0% citation correctness across all answerable questions (capturing necessary surrounding section context with top-$k=5$) and lower retrieval latency (24.6ms over 275 indexed chunks), while maintaining 100% refusal accuracy on out-of-scope question Q6.
- **Comprehensive Test Suite ([`tests/test_day08.py`](tests/test_day08.py)):**
  - Added 16 automated unit tests validating RAG execution, citation deduplication, context sufficiency checks, Q6 refusal, empty query handling, `POST /ask` contract/422 validations, and endpoint regression.
  - Project test suite now totals **79 passing unit tests** across Days 3, 4, 6, 7, and 8.

## Day 9 Progress — AI Agents, Tool Calling & LangGraph Workflow
- **Assigned Developer Tool Identification ([`app/tools.py`](app/tools.py)):**
  - Discovered project-card assigned tool for **SJ-58 (Developer Tools theme)**: `k8s_quantity_converter`.
  - Converts Kubernetes CPU quantities (millicores `500m` $\leftrightarrow$ `0.5` cores) and Memory quantities (binary SI `Ki`, `Mi`, `Gi`, `Ti`; decimal SI `K`, `M`, `G`; plain bytes) into normalized canonical values and human-readable explanations.
  - Implements strict validation and safety bounds: rejects negative numbers, malformed syntax, and quantities exceeding cluster bounds ($> 10,000,000$ cores or $> 10^{18}$ bytes).
- **Safe Read-Only Tool Registry & Dispatcher:**
  - Registered two read-only tools:
    1. `k8s_rag_search`: Retrieval-Augmented Generation over official Kubernetes docs with citation tracking and confidence scoring.
    2. `k8s_quantity_converter`: Resource quantity converter for CPU and memory specs.
  - Defined OpenAI/LangChain-compatible structured schemas (`TOOL_SCHEMAS`) specifying parameters, types, and descriptions.
  - Implemented safe dispatcher `execute_tool(name, arguments)` enforcing schema validation, required arguments, and isolated exception handling.
- **Autonomous Agent Loop ([`app/agent_loop.py`](app/agent_loop.py)):**
  - Built an educational ReAct-style agent loop: User Query $\rightarrow$ Reasoning Planner $\rightarrow$ Tool Action $\rightarrow$ Observation Recording $\rightarrow$ Final Synthesis.
  - Added loop iteration guard (`max_iterations=5`) strictly preventing infinite cycles.
  - Preserves official citations from RAG tool and synthesizes multi-part responses when queries involve multiple steps.
- **LangGraph Stateful Workflow ([`app/graph.py`](app/graph.py)):**
  - Modeled state with `AgentState` TypedDict: `messages`, `current_step`, `tool_calls`, `tool_results`, `citations`, `pending_tool`, `approval_required`, `approved`, `final_answer`, `session_id`.
  - Structured Graph Nodes:
    - `reasoner`: Evaluates user query and prior conversation history to select appropriate tools or prepare direct answers.
    - `approval_gate`: Enforces Human-in-the-Loop (HITL) gate for sensitive operations (`k8s_quantity_converter`), requiring explicit human confirmation before execution.
    - `tool_executor`: Safely executes approved tools via the tool dispatcher.
    - `synthesizer`: Aggregates observations and produces grounded responses with official citations.
  - Conditional Edges & Routing:
    - Dynamic routing from `reasoner` to `approval_gate` or `synthesizer`.
    - Conditional routing from `approval_gate`: pauses workflow if approval is pending, terminates if rejected, and forwards to `tool_executor` if approved.
  - Conversational Session Memory: In-memory session checkpointer store keyed by `session_id`, retaining state across turns so approvals can be submitted asynchronously.
- **Agent Workflow Diagram:**
  ```mermaid
  flowchart TD
    A["User Request<br/>(POST /agent)"] --> B["Reasoner Node<br/>(Analyze query & history)"]
    B -- "Tool Required" --> C{"Approval Gate<br/>(HITL Check)"}
    B -- "Direct Answer" --> D["Synthesizer Node<br/>(Generate Response)"]
    C -- "Safe Tool (k8s_rag_search)" --> E["Tool Executor Node<br/>(Safe Dispatcher)"]
    C -- "k8s_quantity_converter<br/>(approved=None)" --> F["Pause Execution<br/>approval_required=True"]
    C -- "k8s_quantity_converter<br/>(approved=False)" --> G["Rejection Handler<br/>approval_status='rejected'"]
    C -- "k8s_quantity_converter<br/>(approved=True)" --> E
    E --> D
    D --> H["Final Output<br/>Answer + Citations + State"]
    F --> H
    G --> H
  ```
- **FastAPI Agent Endpoint (`POST /agent` in [`app/main.py`](app/main.py)):**
  - Accepts `AgentRequest` (`question: str`, optional `session_id: str`, optional `approved: bool`).
  - Returns `AgentResponse` (`question`, `answer`, `tool_calls`, `citations`, `session_id`, `approval_required`, `approval_status`, `pending_tool`).
  - Updated root endpoint `GET /` to expose `"agent_url": "/agent"`.
- **Comprehensive Test Suite ([`tests/test_day09.py`](tests/test_day09.py)):**
  - Added 23 automated tests covering all 10 required Day 9 scenarios:
    1. RAG question triggers RAG search tool
    2. Quantity question triggers converter tool
    3. Multi-part question triggers both tools
    4. Invalid tool name handling
    5. Invalid tool arguments handling
    6. Tool execution failure handling
    7. Human approval requested when converter tool selected
    8. Human approval rejection stops execution cleanly
    9. Conversation memory retains context across multiple turns
    10. Iteration limit prevents infinite loops
    Plus FastAPI `/agent` endpoint contracts and schema inspection.
  - Project test suite now totals **102 passing unit tests** across Days 3, 4, 6, 7, 8, and 9!

---

## Repository Structure

```text
GenAI/
├── app/
│   ├── __init__.py
│   ├── chunking.py          # Day 7: Document chunking engine for docs & records
│   ├── cli.py               # Day 2: Interactive CLI explorer
│   ├── embed.py             # Day 7: Dense vector embeddings (all-MiniLM-L6-v2 & Mock)
│   ├── fetch.py             # Day 3: Official Kubernetes docs HTTP fetcher
│   ├── ingest.py            # Day 3: Markdown parsing and JSON ingestion pipeline
│   ├── llm.py               # Day 6: Unified LLM provider wrapper (Groq, Gemini, Mock)
│   ├── main.py              # Day 4/6/7/8: FastAPI backend (/chat, /search/semantic, /ask)
│   ├── models.py            # Day 3: Record dataclass and custom exception types
│   ├── rag.py               # Day 8: Grounded RAG pipeline with citations & refusal guardrail
│   ├── records.py           # Day 2/3: Record loading and querying functions
│   ├── smart_search.py      # Day 4: TF-IDF vectorization & Cosine Similarity search
│   └── vectorstore.py       # Day 7: Persistent ChromaDB vector database manager
├── analysis/
│   ├── __init__.py
│   └── explore.py           # Day 4: Pandas data exploration and insights
├── data/
│   ├── __init__.py
│   ├── manifest.json        # Fetch metadata provenance (in data/raw/)
│   ├── raw/                 # Downloaded raw documentation files
│   ├── records.json         # Standardized JSON knowledge base (18 records)
│   └── questions.json       # Persisted student questions
├── docs/
│   ├── how_llms_work.md     # Day 5: LLM fundamentals, Transformer & attention guide
│   └── checkpoint_1.md      # Day 5: Checkpoint 1 review & viva preparation guide
├── eval/
│   ├── eval_results.json    # Day 8: Multi-configuration benchmark execution metrics
│   ├── eval_set.json        # Day 8: 15-question evaluation benchmark dataset
│   ├── prompt_compare.md    # Day 6: Systematic Prompt A vs. Prompt B comparison
│   ├── questions.json       # Day 5: 10 real user evaluation questions (with Q6 unanswerable)
│   ├── rag_comparison.md    # Day 8: Detailed Config A vs Config B comparison report
│   ├── run_eval.py          # Day 8: Automated evaluation and benchmark runner
│   └── search_results.md    # Day 7: Semantic Search vs. TF-IDF benchmark comparison
├── prompts/
│   ├── explain_concept.md   # Day 6: Structured concept explanation prompt template
│   ├── kubectl_helper.md    # Day 6: Practical kubectl command helper prompt template
│   ├── rag_system_prompt.md # Day 8: Grounded RAG system prompt with citation directives
│   └── system_prompt.md     # Day 6: Master system prompt enforcing persona & JSON schema
├── tests/
│   ├── __init__.py
│   ├── test_day03.py        # Day 3 test suite (16 tests)
│   ├── test_day04.py        # Day 4 test suite (18 tests)
│   ├── test_day06.py        # Day 6 test suite (13 tests)
│   ├── test_day07.py        # Day 7 test suite (16 tests)
│   └── test_day08.py        # Day 8 test suite (16 tests)
├── .env.example             # Day 6: Environment configuration template
├── day01_intro.py           # Day 1 introduction script
├── day01_menu.py            # Day 1 menu script
├── requirements.txt         # Project dependencies (FastAPI, Groq, ChromaDB, etc.)
├── README.md                # Documentation
└── .gitignore
```

---

## API Endpoints Reference

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/` | Welcome message and API overview | `200 OK` |
| `GET` | `/health` | API operational health, record count, and LLM provider | `200 OK` |
| `GET` | `/records?limit=` | List all records, optionally limited (`1 <= limit <= 100`) | `200 OK`, `422 Unprocessable` |
| `GET` | `/records/{record_id}` | Retrieve single Kubernetes concept by ID | `200 OK`, `404 Not Found` |
| `GET` | `/search?q=` | Smart TF-IDF search ranking top 3 relevant concepts | `200 OK` |
| `GET` | `/search/semantic?q=&limit=&category=` | Dense vector semantic search using ChromaDB and Sentence Transformers | `200 OK`, `422 Unprocessable` |
| `POST` | `/questions` | Submit a student question; appends to `data/questions.json` | `201 Created`, `422 Unprocessable` |
| `POST` | `/chat` | Chat with KubeCoach LLM assistant; returns structured JSON | `200 OK`, `422 Unprocessable`, `429 Too Many Requests`, `502 Bad Gateway`, `503 Unavailable`, `504 Gateway Timeout` |
| `POST` | `/ask` | Grounded RAG question answering with verified citations and honest refusal guardrail | `200 OK`, `422 Unprocessable`, `429 Too Many Requests`, `502 Bad Gateway`, `503 Unavailable`, `504 Gateway Timeout` |
| `POST` | `/agent` | Autonomous AI Agent workflow with LangGraph, RAG documentation retrieval, and HITL approval gate | `200 OK`, `422 Unprocessable`, `500 Internal Error` |

---

## How to Run

From the `GenAI` repository root:

### 1. Setup Virtual Environment & Dependencies

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install dependencies (requests, fastapi, uvicorn, pydantic, pandas, scikit-learn, httpx, python-dotenv, groq, chromadb, sentence-transformers)
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables

```bash
# Copy the template to .env
cp .env.example .env

# Edit .env with your preferred provider and API key:
# LLM_PROVIDER=groq     # or "gemini", or "mock" (offline testing default)
# GROQ_API_KEY=gsk_...
# GEMINI_API_KEY=AIzaSy_...
```

### 3. Start the FastAPI Server (Uvicorn)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Open API: `http://127.0.0.1:8000`
- Interactive Swagger UI Documentation: `http://127.0.0.1:8000/docs`
- Alternative ReDoc Documentation: `http://127.0.0.1:8000/redoc`

### 4. Example API Requests

```bash
# Health check (includes provider status)
curl -X GET http://127.0.0.1:8000/health

# Get first 3 records
curl -X GET "http://127.0.0.1:8000/records?limit=3"

# Get record by ID
curl -X GET http://127.0.0.1:8000/records/pod

# Smart TF-IDF search (lexical/keyword)
curl -X GET "http://127.0.0.1:8000/search?q=how+to+rollout+deployments"

# Semantic vector search (Day 7: dense embedding search via ChromaDB)
curl -X GET "http://127.0.0.1:8000/search/semantic?q=pod+is+crashing+repeatedly&limit=3"

# Grounded RAG question answering with citations (Day 8: POST /ask)
curl -X POST http://127.0.0.1:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What is a Pod and what command lists running pods?", "top_k": 3}'

# Out-of-scope query returning honest refusal with zero fake citations (Day 8: Q6)
curl -X POST http://127.0.0.1:8000/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?", "top_k": 3}'

# Submit a student question
curl -X POST http://127.0.0.1:8000/questions \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the difference between a Pod and a Service?", "user_name": "Bhushan"}'

# Chat with LLM assistant (Day 6: returns structured JSON with confidence and follow-up)
curl -X POST http://127.0.0.1:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"query": "What is a Pod and how do I list running pods?"}'
```

Example JSON response from `POST /ask`:
```json
{
  "question": "What is a Pod and what command lists running pods?",
  "answer": "Based on official Kubernetes documentation for Pods (workload):\n\nA Pod is the smallest deployable compute unit in Kubernetes. Replicated Pods are usually created and managed as a group by a workload resource and its controller.\n\nExample command:\n```bash\nkubectl get pods -o wide\n```",
  "citations": [
    {
      "document_title": "Pods",
      "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
      "page": "pods.md",
      "chunk_id": "doc:pods:chunk:001"
    }
  ],
  "retrieved_chunks": [
    {
      "chunk_id": "doc:pods:chunk:001",
      "text": "A Pod is the smallest deployable compute unit in Kubernetes...",
      "similarity": 0.8909,
      "source": "raw/pods.md",
      "page": "pods.md",
      "title": "Pods",
      "category": "workload"
    }
  ],
  "confidence": "high",
  "context_sufficient": true
}
```

Example JSON refusal response from `POST /ask` on out-of-scope question Q6:
```json
{
  "question": "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?",
  "answer": "I don't know based on the provided official Kubernetes documentation. The retrieved documents do not contain sufficient information to answer this question.",
  "citations": [],
  "retrieved_chunks": [],
  "confidence": "low",
  "context_sufficient": false
}
```

#### Test AI Agent Endpoint (`POST /agent`) with cURL:

**Scenario A — Grounded RAG Documentation Search (Autonomous Execution):**
```bash
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"question": "What is a Pod and what command lists pods?"}'
```

**Scenario B — Human-in-the-Loop (HITL) Quantity Converter Lifecycle:**

Step 1: Request conversion (workflow pauses at approval gate):
```bash
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"question": "Convert 500m CPU to cores"}'
```
*Response returns `"approval_required": true`, `"approval_status": "pending"`, and a `"session_id"`.*

Step 2: Submit human approval to proceed with execution:
```bash
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"question": "proceed", "session_id": "<SESSION_ID>", "approved": true}'
```
*Response executes tool and returns `"0.5 core(s) (500 millicores)"` with `"approval_status": "approved"`.*

Step 3: Reject execution (optional rejection path):
```bash
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{"question": "cancel", "session_id": "<SESSION_ID>", "approved": false}'
```
*Response aborts tool execution cleanly with `"approval_status": "rejected"`.*

### 5. Run Day 9 Agent Loop & LangGraph Workflow CLI

```bash
# Run educational agent loop
python -m app.agent_loop

# Run stateful LangGraph agent
python -m app.graph
```

### 6. Run Day 8 Multi-Configuration RAG Evaluation Benchmark

```bash
# Evaluates Configuration A vs. Configuration B across all 15 questions in eval/eval_set.json
python -m eval.run_eval
```

### 6. Run Pandas Exploratory Analysis

```bash
python -m analysis.explore
```

### 7. Run TF-IDF Smart Search CLI Tester

```bash
python -m app.smart_search
```

### 9. Run Document Chunking & ChromaDB Vector Indexer

```bash
# Ingest official documentation and records into persistent ChromaDB
python -m app.vectorstore
```

### 10. Run Complete Test Suite (Days 3, 4, 6, 7, 8 & 9)

```bash
python -m unittest discover tests -v
```
*(Runs all 102 automated unit tests across models, ingestion, REST endpoints, smart search, LLM providers, chunking, embeddings, ChromaDB, RAG pipeline, agent tools, loop, and LangGraph workflow)*

### 11. Run Earlier Day Modules

```bash
# Day 1
python day01_intro.py
python day01_menu.py

# Day 2 CLI
python -m app.cli

# Day 3 Fetch & Ingest
python -m app.fetch
python -m app.ingest
```
