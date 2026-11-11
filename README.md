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

---

## Repository Structure

```text
GenAI/
├── app/
│   ├── __init__.py
│   ├── cli.py               # Day 2: Interactive CLI explorer
│   ├── fetch.py             # Day 3: Official Kubernetes docs HTTP fetcher
│   ├── ingest.py            # Day 3: Markdown parsing and JSON ingestion pipeline
│   ├── models.py            # Day 3: Record dataclass and custom exception types
│   ├── records.py           # Day 2/3: Record loading and querying functions
│   ├── main.py              # Day 4: FastAPI REST API backend
│   └── smart_search.py      # Day 4: TF-IDF vectorization & Cosine Similarity search
├── analysis/
│   ├── __init__.py
│   └── explore.py           # Day 4: Pandas data exploration and insights
├── data/
│   ├── __init__.py
│   ├── manifest.json        # Fetch metadata provenance (in data/raw/)
│   ├── raw/                 # Downloaded raw documentation files
│   ├── records.json         # Standardized JSON knowledge base
│   └── questions.json       # Persisted student questions
├── tests/
│   ├── __init__.py
│   ├── test_day03.py        # Day 3 test suite (16 tests)
│   └── test_day04.py        # Day 4 test suite (18 tests)
├── day01_intro.py           # Day 1 introduction script
├── day01_menu.py            # Day 1 menu script
├── requirements.txt         # Project dependencies
├── README.md                # Documentation
└── .gitignore
```

---

## API Endpoints Reference

| Method | Endpoint | Description | Status Codes |
|---|---|---|---|
| `GET` | `/` | Welcome message and API overview | `200 OK` |
| `GET` | `/health` | API operational health and record count | `200 OK` |
| `GET` | `/records?limit=` | List all records, optionally limited (`1 <= limit <= 100`) | `200 OK`, `422 Unprocessable` |
| `GET` | `/records/{record_id}` | Retrieve single Kubernetes concept by ID | `200 OK`, `404 Not Found` |
| `GET` | `/search?q=` | Smart TF-IDF search ranking top 3 relevant concepts | `200 OK` |
| `POST` | `/questions` | Submit a student question; appends to `data/questions.json` | `201 Created`, `422 Unprocessable` |

---

## How to Run

From the `GenAI` repository root:

### 1. Setup Virtual Environment & Dependencies

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install dependencies (requests, fastapi, uvicorn, pydantic, pandas, scikit-learn, httpx)
python -m pip install -r requirements.txt
```

### 2. Start the FastAPI Server (Uvicorn)

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Open API: `http://127.0.0.1:8000`
- Interactive Swagger UI Documentation: `http://127.0.0.1:8000/docs`
- Alternative ReDoc Documentation: `http://127.0.0.1:8000/redoc`

### 3. Example API Requests

```bash
# Health check
curl -X GET http://127.0.0.1:8000/health

# Get first 3 records
curl -X GET "http://127.0.0.1:8000/records?limit=3"

# Get record by ID
curl -X GET http://127.0.0.1:8000/records/pod

# Smart TF-IDF search
curl -X GET "http://127.0.0.1:8000/search?q=how+to+rollout+deployments"

# Submit a question
curl -X POST http://127.0.0.1:8000/questions \
     -H "Content-Type: application/json" \
     -d '{"question": "What is the difference between a Pod and a Service?", "user_name": "Bhushan"}'
```

### 4. Run Pandas Exploratory Analysis

```bash
python -m analysis.explore
```

### 5. Run TF-IDF Smart Search CLI Tester

```bash
python -m app.smart_search
```

### 6. Run Complete Test Suite (Days 3 & 4)

```bash
python -m unittest discover tests
```
*(Runs all 34 automated unit tests)*

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
