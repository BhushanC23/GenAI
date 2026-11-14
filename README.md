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

---

## Repository Structure

```text
GenAI/
├── app/
│   ├── __init__.py
│   ├── cli.py               # Day 2: Interactive CLI explorer
│   ├── fetch.py             # Day 3: Official Kubernetes docs HTTP fetcher
│   ├── ingest.py            # Day 3: Markdown parsing and JSON ingestion pipeline
│   ├── llm.py               # Day 6: Unified LLM provider wrapper (Groq, Gemini, Mock)
│   ├── main.py              # Day 4/6: FastAPI REST API backend & /chat endpoint
│   ├── models.py            # Day 3: Record dataclass and custom exception types
│   ├── records.py           # Day 2/3: Record loading and querying functions
│   └── smart_search.py      # Day 4: TF-IDF vectorization & Cosine Similarity search
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
│   ├── prompt_compare.md    # Day 6: Systematic Prompt A vs. Prompt B comparison
│   └── questions.json       # Day 5: 10 real user evaluation questions (with Q6 unanswerable)
├── prompts/
│   ├── explain_concept.md   # Day 6: Structured concept explanation prompt template
│   ├── kubectl_helper.md    # Day 6: Practical kubectl command helper prompt template
│   └── system_prompt.md     # Day 6: Master system prompt enforcing persona & JSON schema
├── tests/
│   ├── __init__.py
│   ├── test_day03.py        # Day 3 test suite (16 tests)
│   ├── test_day04.py        # Day 4 test suite (18 tests)
│   └── test_day06.py        # Day 6 test suite (13 tests)
├── .env.example             # Day 6: Environment configuration template
├── day01_intro.py           # Day 1 introduction script
├── day01_menu.py            # Day 1 menu script
├── requirements.txt         # Project dependencies (FastAPI, Groq, Pandas, etc.)
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
| `POST` | `/questions` | Submit a student question; appends to `data/questions.json` | `201 Created`, `422 Unprocessable` |
| `POST` | `/chat` | Chat with KubeCoach LLM assistant; returns structured JSON | `200 OK`, `422 Unprocessable`, `429 Too Many Requests`, `502 Bad Gateway`, `503 Unavailable`, `504 Gateway Timeout` |

---

## How to Run

From the `GenAI` repository root:

### 1. Setup Virtual Environment & Dependencies

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install dependencies (requests, fastapi, uvicorn, pydantic, pandas, scikit-learn, httpx, python-dotenv, groq)
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

# Smart TF-IDF search
curl -X GET "http://127.0.0.1:8000/search?q=how+to+rollout+deployments"

# Submit a student question
curl -X POST http://127.0.0.1:8000/questions \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the difference between a Pod and a Service?", "user_name": "Bhushan"}'

# Chat with LLM assistant (Day 6: returns structured JSON with confidence and follow-up)
curl -X POST http://127.0.0.1:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"query": "What is a Pod and how do I list running pods?"}'
```

Example JSON response from `POST /chat`:
```json
{
  "answer": "A Pod is the smallest deployable compute unit in Kubernetes representing a single instance of a running process.\n\nTo list running pods with wide output, execute:\n```bash\nkubectl get pods -o wide\n```",
  "confidence": "high",
  "follow_up": "Would you like to know how Deployments manage Pod replica sets and rolling updates?",
  "provider": "mock",
  "model": "grounded-seed-knowledge-base",
  "grounded_records": ["pod"]
}
```

### 5. Run Pandas Exploratory Analysis

```bash
python -m analysis.explore
```

### 6. Run TF-IDF Smart Search CLI Tester

```bash
python -m app.smart_search
```

### 7. Run Complete Test Suite (Days 3, 4 & 6)

```bash
python -m unittest discover tests -v
```
*(Runs all 47 automated unit tests across models, ingestion, REST endpoints, smart search, and LLM providers)*

### 7. Run Earlier Day Modules

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
