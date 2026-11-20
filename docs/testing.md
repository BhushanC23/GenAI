# KubeCoach — Comprehensive Testing & Quality Assurance Guide

### Project ID: SJ-58
### Theme: Developer Tools
### Student: Bhushan Kailas Chaturbhuj (Reg. No: 2125PCAM1038)
### Day 11 Deliverable

---

## 1. Overview & Testing Philosophy

KubeCoach is an educational developer tool explaining Kubernetes concepts and `kubectl` commands to final-year students preparing for DevOps interviews. Because accuracy and dependability are critical in educational systems, the testing architecture ensures:

1. **Deterministic Grounding:** Numerical quantity conversions (CPU cores, millicores, binary SI `Gi/Mi`, decimal SI `G/M`) are verified using deterministic Python `Decimal` arithmetic—never relying on LLM math.
2. **Zero-Hallucination & Refusal Integrity:** Out-of-scope technologies (such as Istio Service Mesh with mTLS in question **Q6**) are rigorously tested to guarantee that the RAG pipeline admits insufficient context honestly (`citations: []`, `context_sufficient: false`) rather than fabricating answers.
3. **Reproducibility & Zero Cost:** All test suites run locally without requiring live network access, active internet connectivity, paid LLM API keys, or pre-existing cluster states. External dependencies (Groq/Gemini APIs, ChromaDB disk operations, HTTP downloads) are cleanly mocked or use offline fallback providers.
4. **Backward Compatibility:** All new test additions extend the existing test suite without breaking any previous milestones from Days 3 through 10.

---

## 2. Testing Frameworks & Configuration

KubeCoach supports dual test execution frameworks:
- **`pytest` (Recommended Modern Test Runner):** High-speed test collection, detailed assertion formatting, and integrated code coverage measurement via `pytest-cov`. Configured via `pytest.ini`.
- **`unittest` (Python Standard Library):** Built-in runner requiring zero external packages (`python -m unittest discover tests -v`).

### Test Configuration (`pytest.ini`)
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
    ignore::UserWarning
```

---

## 3. Installation & Test Execution Commands

### A. Install Dependencies
```bash
# Activate virtual environment
.\.venv311\Scripts\Activate.ps1   # Windows PowerShell
# or: source .venv/bin/activate    # Linux / macOS

# Install project dependencies including test runners
pip install -r requirements.txt
```

### B. Run the Full Test Suite
```bash
# Run all 150 tests using pytest
pytest tests/ -v

# Run all 150 tests using Python standard unittest
python -m unittest discover tests -v

# Run with concise tracebacks
pytest tests/ --tb=short
```

### C. Run Specific Test Suites
```bash
# Run Day 11 Quality Assurance tests (28 tests)
pytest tests/test_day11.py -v
python -m unittest tests/test_day11.py -v

# Run Day 10 UI, client & relationship strip tests (14 tests)
pytest tests/test_day10.py -v

# Run Day 09 Agent, Quantity Converter & LangGraph tests (29 tests)
pytest tests/test_day09.py -v

# Run Day 08 RAG pipeline & citation tests (16 tests)
pytest tests/test_day08.py -v
```

### D. Measure Code Coverage
```bash
# Generate terminal coverage report across app/ and ui/
pytest tests/ --cov=app --cov=ui --cov-report=term-missing
```

---

## 4. Test Directory Structure

```text
tests/
├── __init__.py          # Package marker
├── test_day03.py        # 16 tests: Record models, validation, fetcher, ingestion
├── test_day04.py        # 18 tests: FastAPI REST endpoints, Pydantic schemas, TF-IDF smart search
├── test_day06.py        # 13 tests: Multi-provider LLM wrapper, mock provider, /chat endpoint
├── test_day07.py        # 16 tests: Document chunking, MiniLM embeddings, ChromaDB search
├── test_day08.py        # 16 tests: RAG pipeline, citations, Q6 refusal guardrail, /ask endpoint
├── test_day09.py        # 29 tests: Quantity converter, ReAct loop, LangGraph HITL interrupt/resume
├── test_day10.py        # 14 tests: Streamlit client, relationship strip, feedback persistence
└── test_day11.py        # 28 tests: Comprehensive end-to-end QA, edge cases, boundary testing
```

---

## 5. Test Categories & Verification Scope

The 150 tests span 7 distinct architectural categories:

### Category A: Core Python Functions & Data Models
- **Validation Boundaries:** Tests strict validation in `Record` dataclass (`models.py`), auto-slug generation, mandatory field enforcement, and rejection of invalid URL protocols (e.g. `ftp://`).
- **Resilience to Corrupted Files:** Validates that `load_records()` handles corrupt JSON or missing files gracefully by falling back to verified seed records.
- **Chunking Edge Cases:** Tests `split_text()` with empty strings, texts shorter than chunk size, zero overlap, and special Unicode/emojis.
- **Text Cleaning:** Verifies `clean_doc_text()` strips Hugo shortcodes and HTML comments while preserving backtick code fences and technical flags.

### Category B: FastAPI REST Endpoints & API Contracts
- **Health Check (`GET /health`):** Verifies HTTP 200 contract, status `"ok"`, and active records count.
- **Pagination & Bounds (`GET /records?limit=`):** Tests boundary limits (`limit=1`, `limit=100`), and verifies HTTP 422 Unprocessable for boundary violations (`limit=0`, `limit=101`, `limit=-3`).
- **Path Parameters (`GET /records/{id}`):** Tests valid IDs (`/records/pod`) and validates HTTP 404 Not Found for non-existent concepts.
- **Search Query Validation (`GET /search`):** Tests valid queries, empty queries (`q=`), whitespace queries, and single-character queries.
- **HTTP Method Not Allowed (405):** Verifies that incorrect HTTP methods (e.g., `POST /health`, `GET /ask`, `PUT /records`) safely return HTTP 405 Method Not Allowed.

### Category C: Data Ingestion & Network Resilience
- **Network Failure Isolation:** Mocks `requests.get` to raise `requests.exceptions.ConnectionError`, `Timeout`, and `HTTPError (500)`, confirming `fetch_url()` logs error context and raises appropriately for pipeline handling.
- **Malformed Frontmatter:** Verifies `parse_frontmatter_and_overview()` extracts content even when Markdown documents lack standard YAML delimiters.
- **Ingestion Idempotence:** Confirms running ingestion multiple times updates data cleanly without creating duplicate record IDs.

### Category D: Search & Retrieval Systems
- **Lexical TF-IDF Search (`app/smart_search.py`):** Tests queries composed entirely of English stop words (`what is the and or`), non-matching gibberish, and validates corpus structure weighting ID and title heavily.
- **Semantic Vector Search (`app/vectorstore.py`):** Tests cosine similarity calculation, score normalization ($[0.0, 1.0]$), and category filtering (`category=storage`).

### Category E: RAG Pipeline, Grounding & Citations
- **Grounded Answering:** Verifies `POST /ask` answers known Kubernetes questions with factual excerpts and verified citations (`source_url`, `document_title`).
- **Refusal Guardrail (Q6):** Tests out-of-scope question ("How do I configure an Istio Service Mesh with Mutual TLS across multi-cluster deployments?"), verifying `context_sufficient == False`, refusal answer ("I don't know based on..."), and `citations == []`.
- **Input Validation:** Confirms empty or whitespace questions return HTTP 422.

### Category F: AI Agent, Tools, Quantity Converter & HITL Safety
- **Deterministic Quantity Conversion (`k8s_quantity_converter`):**
  - Zero values: `0m` CPU $\rightarrow$ 0 cores, `0` $\rightarrow$ 0m, `0Mi` $\rightarrow$ 0 bytes.
  - Equality comparisons: `500m` vs `0.5` cores $\rightarrow$ `"equal"`, difference 0. `1024Mi` vs `1Gi` $\rightarrow$ `"equal"`.
  - Negative values & invalid suffixes: `-500m`, `128MegaBytes`, `ten_gigabytes` cleanly rejected with `success: false` and explanatory errors.
- **Tool Registry Dispatcher:** Rejects unregistered tool calls (e.g. `launch_kubernetes_missile`), validates tool schemas, and prevents unexpected arguments.
- **ReAct Agent Max Iterations:** Confirms the hand-written agent loop terminates cleanly when reaching `max_iterations = 3`, setting `stopped_by_limit = True` and appending safety notes without hanging.
- **LangGraph Human-In-The-Loop (HITL):** Tests pausing at `approval_node` on quantity comparisons (`approval_required = True`), and verifies that human rejection (`approved = False`) skips tool execution and records rejection status.

### Category G: Streamlit UI Client Resilience & Components
- **API Client Resilience (`ui/api_client.py`):** Mocks connection failures to FastAPI backend, confirming `check_health()` returns `connected: false` and descriptive errors without crashing the UI.
- **Relationship Strip Engine (`ui/relationships.py`):** Tests case-insensitive object detection (`DEPLOYMENTS`, `PODS`, `SERVICES`), verified strip selection, and confirms refusal responses never render relationship strips.
- **Feedback Duplicate Prevention:** Tests `POST /feedback`, verifying first rating returns HTTP 201 Created and subsequent ratings for the same response ID return HTTP 409 Conflict.

---

## 6. Mocking & Test Isolation Strategy

Tests achieve high speed and reproducibility through isolated test environments:

| Dependency | Isolation Mechanism | Reason |
|---|---|---|
| **External LLMs (Groq, Gemini)** | `MockLLMProvider` + `unittest.mock.patch` | Eliminates external API keys, rate limits, and network latency. |
| **HuggingFace Embeddings** | `MockEmbeddingProvider` (seed hashing) for unit tests; singleton MiniLM for integration tests | Ensures zero network calls to HuggingFace during testing. |
| **HTTP Downloads** | `unittest.mock.patch("requests.get")` | Simulates timeouts, 404s, 500s, and connection drops deterministically. |
| **Feedback File Storage** | `tempfile.TemporaryDirectory()` + path overrides | Prevents test execution from modifying `data/feedback.json`. |
| **LangGraph Multi-turn State** | Unique `session_id` per test + in-memory `MemorySaver` | Guarantees test isolation across concurrent runs. |

---

## 7. Actual Verified Test Execution Results

Executed on Python 3.11.9 (Windows 64-bit):

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\bhushan chaturbhuj\Desktop\KubeCoach\GenAI
configfile: pytest.ini
plugins: anyio-4.16.0, langsmith-0.15.0, cov-7.1.0
collected 150 items

tests/test_day03.py ................                                     [ 10%]
tests/test_day04.py ..................                                   [ 22%]
tests/test_day06.py .............                                        [ 31%]
tests/test_day07.py ................                                     [ 42%]
tests/test_day08.py ................                                     [ 52%]
tests/test_day09.py .............................                        [ 72%]
tests/test_day10.py ..............                                       [ 81%]
tests/test_day11.py ............................                         [100%]

======================= 150 passed in 85.77s (0:01:25) ========================
```

### Verified Code Coverage Metrics (`pytest-cov`)

| Module | Statements | Missed | Coverage | Key Tested Components |
|---|---|---|---|---|
| `app/models.py` | 52 | 5 | **90%** | Record dataclass, validation, slugification, custom exceptions |
| `app/graph.py` | 212 | 23 | **89%** | LangGraph StateGraph, MemorySaver, interrupt & resume nodes |
| `app/chunking.py` | 166 | 18 | **89%** | Sliding-window text chunker, markdown cleaner, metadata |
| `app/ui/api_client.py` | 81 | 10 | **88%** | HTTP client connecting Streamlit to FastAPI with error mapping |
| `app/ui/relationships.py` | 81 | 10 | **88%** | Kubernetes Object Relationship Strip engine & HTML generator |
| `app/records.py` | 55 | 8 | **85%** | Record loading, query helpers, category counting |
| `app/ingest.py` | 132 | 24 | **82%** | Markdown parsing, Hugo shortcode cleaner, ingestion pipeline |
| `app/tools.py` | 260 | 51 | **80%** | Quantity converter arithmetic, RAG search tool, schema validation |
| `app/embed.py` | 106 | 23 | **78%** | SentenceTransformer singleton and offline Mock embedder |
| `app/rag.py` | 156 | 35 | **78%** | Grounded answer generation, citations, refusal guardrail |
| `app/main.py` | 340 | 78 | **77%** | All FastAPI REST routes, schemas, error handlers, feedback API |
| `app/vectorstore.py` | 139 | 35 | **75%** | Persistent ChromaDB collection, similarity queries, disk sync |
| `app/smart_search.py` | 62 | 17 | **73%** | TF-IDF vectorizer and Cosine Similarity smart search |
| `app/agent_loop.py` | 202 | 59 | **71%** | Hand-written ReAct loop, iteration bounds, execution trace |
| `app/llm.py` | 140 | 63 | **55%** | Unified provider wrapper, JSON parsing, mock fallback |
| `ui/app.py` | 237 | 117 | **51%** | Streamlit UI interactive elements, state, and rendering |
| `app/fetch.py` | 65 | 32 | **51%** | Documentation downloader with timeouts and exception logging |
| **TOTAL** | **2540** | **658** | **74%** | **Overall Project Code Coverage** |

---

## 8. Viva & Evaluation Talking Points

When presenting Day 11 Quality Assurance during your college viva:

1. **Why dual test runners (`unittest` + `pytest`)?**
   `unittest` is built into standard Python (guaranteeing zero external requirements for basic checks), while `pytest` offers advanced test discovery, concise failure diffs, and integration with `pytest-cov` for measuring real statement coverage.
2. **How does KubeCoach prevent LLM hallucinations during testing?**
   Tests verify that unanswerable question Q6 (Istio mTLS) returns an explicit refusal with zero fabricated citations. The test asserts `context_sufficient == False` and `len(citations) == 0`.
3. **Why is the Quantity Converter tested with deterministic Python math?**
   Kubernetes CPU and Memory limits cannot tolerate LLM arithmetic hallucinations. By using Python's `decimal.Decimal` module, the tests verify exact byte calculations (e.g. `1Gi = 1024Mi = 1,073,741,824 bytes` vs `1G = 1,000,000,000 bytes`).
4. **How are external dependencies isolated?**
   External network downloads, LLM APIs (Groq/Gemini), and disk writes are mocked using `unittest.mock.patch` and `tempfile.TemporaryDirectory`, making the test suite 100% reproducible across different environments.
