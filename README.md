# KubeCoach

### Project ID: SJ-58
### Theme: Developer Tools

## About
KubeCoach is an educational developer learning tool designed to explain Kubernetes concepts and kubectl commands in simple English using official Kubernetes documentation.

## Target Users
Final-year IT students preparing for DevOps interviews and beginners practicing Kubernetes workloads.

## Problem
Official Kubernetes documentation is extensive and technically dense. Beginners often struggle to understand what each object does, which kubectl command to run, and how defaults are configured. KubeCoach provides structured, documentation-grounded explanations.

## Data Source
- Official Documentation Concepts: https://kubernetes.io/docs/concepts/
- Official Documentation Source Repository: https://github.com/kubernetes/website

---

## Day 1 Progress
- Created `day01_intro.py` introducing the project and student interactions.
- Created `day01_menu.py` with an interactive while-loop menu.
- Practised Python variables, data types, input, f-strings, conditional branching, and loop control.

## Day 2 Progress
- Added 18 structured Kubernetes records based on official documentation.
- Implemented list and dictionary data handling.
- Implemented keyword search and category counting.
- Organised reusable functions in `app/records.py`.
- Established a modular `app/` and `data/` project structure.
- Built an interactive terminal CLI (`app/cli.py`) for querying Kubernetes records.

## Day 3 Progress
- **Dataclass & OOP Modeling (`app/models.py`):**
  - Implemented the `Record` `@dataclass` representing standard knowledge records (`page_title`, `category`, `one_line_definition`, `key_kubectl_command`, `limit_or_default`, `source_url`, and `id`).
  - Added strict data validation and slug generation in `__post_init__`.
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

---

## Repository Structure

```text
GenAI/
├── app/
│   ├── __init__.py
│   ├── cli.py               # Interactive CLI explorer
│   ├── fetch.py             # Official Kubernetes docs HTTP fetcher
│   ├── ingest.py            # Markdown parsing and JSON ingestion pipeline
│   ├── models.py            # Record dataclass and custom exception types
│   └── records.py           # Record loading and querying functions
├── data/
│   ├── __init__.py
│   ├── manifest.json        # Fetch metadata provenance (in data/raw/)
│   ├── raw/                 # Downloaded raw documentation files
│   ├── records.json         # Cleaned, standardized JSON dataset
│   └── sample_records.py    # Seed verified Kubernetes records
├── tests/
│   ├── __init__.py
│   └── test_day03.py        # Automated test suite
├── day01_intro.py           # Day 1 introduction script
├── day01_menu.py            # Day 1 menu script
├── requirements.txt         # Project dependencies
├── README.md                # Documentation
└── .gitignore
```

---

## How to Run

From the `GenAI` repository root:

### 1. Setup Virtual Environment & Dependencies

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows PowerShell:
.\.venv\Scripts\Activate.ps1

# Install Day 3 dependencies
python -m pip install -r requirements.txt
```

### 2. Fetch Official Kubernetes Documentation

Downloads official concept documentation from the Kubernetes website repository into `data/raw/`:

```bash
python -m app.fetch
```

### 3. Run Ingestion Pipeline

Parses raw documentation, normalizes content, validates against dataclass schemas, and outputs `data/records.json`:

```bash
python -m app.ingest
```

### 4. Run Interactive CLI (Day 2 Interface)

Explore Kubernetes records, search by keyword, count by category, or view details by ID:

```bash
python -m app.cli
```

### 5. Run Automated Tests

Execute the unit test suite:

```bash
python -m unittest tests/test_day03.py
```

### 6. Verify Cleaned Dataset

Inspect the generated JSON dataset directly or with Python:

```bash
python -c "import json; data = json.load(open('data/records.json')); print('Loaded records:', len(data))"
```
