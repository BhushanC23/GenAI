# KubeCoach: Progress Tracker

**Project:** KubeCoach (Project ID SJ-58, theme Developer Tools), "Learn Kubernetes in Simple English"
**Student:** Bhushan Kailas Chaturbhuj (MCA, Sanjivani University)
**Repository:** https://github.com/BhushanC23/GenAI (branch `main`)
**Last updated:** Day 14 (24 Nov 2026)

**Objective.** An AI learning assistant that explains Kubernetes in simple English, grounded in official Kubernetes documentation. It combines TF-IDF and semantic search, a retrieval-augmented generation (RAG) pipeline with citations and an honest "I don't know", a LangGraph agent with a deterministic CPU/memory quantity converter and human approval, a FastAPI backend and a Streamlit interface.

**Status labels:** **Completed** (done and checked) | **Partially completed** | **Pending** | **Requires manual verification** (cannot be confirmed from the repository or the audit machine).

How evidence was gathered on Day 14: commits and tags from `git log`; test, lint and evaluation results from commands run that day; GitHub Actions results from the public GitHub API (`api.github.com/repos/BhushanC23/GenAI/actions/runs`); the running API and Streamlit server were started locally and called.

---

## 1. Day 1 to 15 completion tracker

| Day | Topic | Status | Evidence |
|---|---|---|---|
| 1 | Python fundamentals | Completed | `day01_intro.py`, `day01_menu.py`; commit `9ca056f` |
| 2 | Collections, functions, JSON, CLI | Completed | `app/records.py`, `app/cli.py`; commit `bf97406` |
| 3 | Files, ingestion, models, fetch | Completed | `app/fetch.py`, `app/ingest.py`, `app/models.py`, `data/raw/` (6 pages), `data/records.json` (18 records); commit `1334043` |
| 4 | FastAPI, Pandas, TF-IDF search | Completed | `app/main.py`, `app/smart_search.py`, `analysis/explore.py`; commit `3c06cc5`, tag `week-1` |
| 5 | LLM fundamentals, Checkpoint 1 | Completed | `docs/how_llms_work.md`, `eval/questions.json`; commit `6582e7f`, tag `checkpoint-1` |
| 6 | LLM integration, prompts | Completed | `app/llm.py` (Groq, Gemini, mock), `prompts/`, `POST /chat`; commit `c7d048c`. Live Groq/Gemini calls **not re-tested on Day 14** (no API key) |
| 7 | Embeddings, ChromaDB | Completed | `app/chunking.py`, `app/embed.py`, `app/vectorstore.py`, `GET /search/semantic`; commit `a97711e` |
| 8 | RAG, citations, evaluation | Completed | `app/rag.py`, `POST /ask`, `eval/eval_set.json` (15 rows), `eval/run_eval.py`; commit `ab41e4c`. Re-run on Day 14 (see section 5) |
| 9 | Agent, tools, LangGraph, approval | Completed | `app/tools.py`, `app/agent_loop.py`, `app/graph.py`, `POST /agent`, `POST /agent/approve`; commits `f6fb1a2`, `04dc2b1`. Approve/reject flow re-checked against the running API on Day 14 |
| 10 | Streamlit UI, Checkpoint 2 | Completed | `ui/app.py`, `ui/relationships.py`, `docs/screenshots/kubecoach-day10.png`, `docs/checkpoint2_demo.md`; commit `37f08ad`, tag `checkpoint-2`. Streamlit server answered HTTP 200 on Day 14; visual click-through is **Requires manual verification** |
| 11 | Testing and QA | Completed | `tests/`, `pytest.ini`, `docs/testing.md`; commit `9334506`. Day 14 result: 162 passed |
| 12 | Docker, Compose, CI start, deploy config | Partially completed | `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `render.yaml`, PR #1 merged (`8d0900f`). Render and Hugging Face deployments: **Requires manual verification** (see section 4) |
| 13 | CI/CD, GHCR, observability, resume | Completed | `.github/workflows/ci.yml`, `docs/ci_cd.md`, `docs/resume.md`, `/cache/stats`; commits `bb67113`, `7a390c1`, `63b2c17`, `7b4b5ce`. GitHub Actions run #8 on `main` succeeded, including GHCR push (section 4) |
| 14 | Interview preparation + build sprint | **Completed** | `docs/interview.md`, `PROGRESS.md`, audit fixes and 8 new tests (section 6). Commit prefix `day-14:`; tag `day-14` |
| 15 | Final evaluation and presentation | Pending | Not confirmed by the repository or the training plan (`TRAINING_MASTER_PLAN.md` lists the official task card as not supplied). Not marked complete |

---

## 2. Main project milestones

1. Day 3: official Kubernetes pages downloaded and cleaned into structured records.
2. Day 4: working FastAPI service with TF-IDF search (`week-1`).
3. Day 5: LLM fundamentals and evaluation questions, including the unanswerable Q6 (`checkpoint-1`).
4. Day 7: embeddings plus persistent ChromaDB semantic search.
5. Day 8: grounded RAG with citations, honest refusal, and a 15-question evaluation.
6. Day 9: tool-calling agent, LangGraph state graph, real pause/resume approval.
7. Day 10: Streamlit UI with citations, relationship strip, and feedback (`checkpoint-2`).
8. Days 11 to 13: automated tests, Docker, GitHub Actions, GHCR image, query cache.
9. Day 14: interview material and a risk-based audit that fixed a stale index, frontmatter leakage, an over-permissive answer rule, and a crashing evaluation script.

## 3. Important files and modules

| Area | Files |
|---|---|
| API | `app/main.py` (routes, validation, cache, feedback) |
| RAG | `app/rag.py` (retrieval, sufficiency rule, citations), `app/chunking.py`, `app/embed.py`, `app/vectorstore.py` |
| Search | `app/smart_search.py` (TF-IDF), `app/records.py` |
| LLM | `app/llm.py` (Groq, Gemini, mock), `prompts/` |
| Agent | `app/tools.py` (allow-listed tools, `Decimal` converter), `app/agent_loop.py`, `app/graph.py` (LangGraph) |
| UI | `ui/app.py`, `ui/api_client.py`, `ui/relationships.py` |
| Data | `data/raw/*.md`, `data/records.json`, `data/chroma_db/` (generated, git-ignored) |
| Quality | `tests/` (162 tests), `eval/run_eval.py`, `eval/eval_set.json`, `ruff.toml`, `pytest.ini` |
| Delivery | `Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.dockerignore`, `.gitattributes`, `.github/workflows/ci.yml`, `render.yaml` |
| Docs | `README.md`, `docs/interview.md`, `docs/ci_cd.md`, `docs/docker.md`, `docs/testing.md`, `docs/resume.md`, `docs/day09_architecture.md` |

## 4. Testing, Docker and CI/CD status

### Testing: Completed (verified on Day 14)

| Check | Command | Result |
|---|---|---|
| Syntax | `python -m compileall -q app tests ui eval analysis day01_intro.py day01_menu.py` | exit 0 |
| Lint | `ruff check .` | All checks passed |
| Tests | `pytest tests/ -q --cov=app --cov=ui` (Python 3.11.9) | **162 passed** in 87 s; total coverage **75%** (lowest: `app/llm.py` 55%, `ui/app.py` 51%, `app/cli.py` 0%) |
| Evaluation | `python -m eval.run_eval` | exit 0; Q6 refused with 0 citations in both configurations; retrieval 86.7%, citation 100%, keyword recall about 32% (the two configurations are tied) |
| Live API smoke test | local `uvicorn`, real embeddings, mock LLM | `/health`, `/search`, `/search/semantic`, `/ask` (10 questions), `/agent` approve and reject, 422/404/409 error cases all behaved as expected |

Before the Day 14 fixes the suite had 154 passing tests; the earlier "150 tests" figures in older documents are historical.

### Docker: Partially completed, local run Requires manual verification

- `Dockerfile` reviewed: `python:3.11-slim`, single stage, non-root user `kubecoach` (UID 1000), `HEALTHCHECK` on `/health`, ports 8000 and 8501, entrypoint modes `api`, `ui`, `all`, `test`. Secrets are excluded by `.dockerignore`.
- The Dockerfile change that was uncommitted when Day 14 started (CPU-only PyTorch, copy `tests/` and `docs/`) is committed on Day 14.
- **Local image build and container run were not completed.** Docker Desktop on the audit machine was not running at the start, and it stopped working (read-only filesystem, "unable to start") when the C: drive ran out of free space during the builds. One local build from the Desktop folder produced an image with 0-byte files, so it proved nothing. Please free disk space, restart Docker Desktop, run `docker image rm kubecoach-day14:local kubecoach-day14:ctx` and `docker builder prune` to remove the leftovers of the audit, then run `docker build -t kubecoach .` and `docker run -p 8000:8000 kubecoach`.
- The build **was** verified by GitHub Actions on the Dockerfile as committed before Day 14 (run #8 below).

### CI/CD: Completed for run #8; the Day 14 commit Requires manual verification

Verified from the GitHub API on Day 14:

| Run | Commit | Event | Result |
|---|---|---|---|
| #1, #2 | `376a8d2` | push and pull request on `feature/day-12-ci-cd` | success |
| #3 to #7 | `8d0900f` ... `63b2c17` | push to `main` | success |
| **#8** (id 45056903970) | `7b4b5ce` (Day 13 head) | push to `main` | **success**, 15 steps including "Build Docker Container", "Log in to GHCR" and "Tag and Push Docker Image to GHCR" |

- GHCR: the package page `github.com/BhushanC23/GenAI/pkgs/container/genai` is public and lists `docker pull ghcr.io/bhushanc23/genai:7b4b5cec400c1211e5a1139010d7ab9a71d44f20`.
- Workflow review: triggers are `push` (`main`, `feature/**`), `pull_request` (to `main`) and `workflow_dispatch`; timeout 15 minutes; Python 3.11; GHCR login and push run only on a push to `main`. Note that `packages: write` is granted at workflow level to every step. A separate publish job would be safer (listed in section 7).
- The run for the Day 14 commit is **Requires manual verification**: check https://github.com/BhushanC23/GenAI/actions after the push.
- Render (`https://kubecoach.onrender.com/health`) did not answer within 30 s from the audit machine (a free-tier cold start is possible) and Hugging Face (`huggingface.co/spaces/BhushanC23/KubeCoach`) returned HTTP 401: both **Requires manual verification**.

## 5. Day 14 audit: issues found and fixed

| # | Root cause | Impact | Fix | Verification |
|---|---|---|---|---|
| 1 | A ChromaDB index from an older chunker was reused forever (`index_documents` skipped when the count was above 0). 417 of 435 IDs were obsolete and no chunk had a `source_url`. | Citations to raw pages showed `raw/pods.md` instead of the official URL. | `sync_chunks()` in `app/vectorstore.py`; used by `index_documents()` (so also at API start-up) and by `eval/run_eval.py`. | Live run rebuilt 427 chunks; all citations were `https://kubernetes.io/docs/...`; tests in `tests/test_day14.py` |
| 2 | YAML frontmatter was not removed before chunking. | Answers began with `reviewers:` and `title:` lines; noise in embeddings. | `clean_markdown_for_chunking()` strips it (`app/chunking.py`). | 0 chunks start with `---`; unit tests |
| 3 | The keyword-coverage rule only applied to queries with 3 or more keywords. | "What is the capital of France?" was answered from Namespaces text (similarity 0.59). | `is_context_sufficient()` refuses when no query keyword appears in the context (`app/rag.py`). | Live `/ask` now refuses; unit tests |
| 4 | `eval/run_eval.py` imported `hnswlib` unconditionally (newer ChromaDB does not install it); it matched `records.json` against strings that never contain it; model loading was counted as latency. | The evaluation script crashed on a clean install; metrics were misleading. | Optional import, record-chunk matching, untimed warm-up query. | `python -m eval.run_eval` exit 0 |
| 5 | No line-ending rule for shell scripts. | A Windows clone with `core.autocrlf=true` would give `docker-entrypoint.sh` CRLF endings, which fail inside Linux containers. | `.gitattributes` (`*.sh` and `Dockerfile` use LF). | File added; not exercised in a container (see Docker) |
| 6 | Documentation claimed unmeasured numbers and features (benchmark latencies, "multi-stage" Docker, "zero hallucinations", chunk size 400 words, `doc:pod:chunk:001` IDs, `python -m app.vectorstore`). | An interviewer could catch the mismatch. | `README.md`, `docs/resume.md`, `docs/ci_cd.md` corrected; measured numbers added. | Reviewed against code |

## 6. Day 14 deliverables

| Item | Status |
|---|---|
| `docs/interview.md` (pitch, hardest-problem STAR story, 10 questions, architecture, stack, demo, safety) | Completed |
| `PROGRESS.md` (this file) | Completed |
| Audit fixes with regression tests (`tests/test_day14.py`, 8 tests) | Completed |
| README update (Day 14 section, limitations, future improvements, corrected numbers) | Completed |
| Commit with prefix `day-14:` and tag `day-14` pushed to `origin/main` | Completed when the push is verified (see `git log` and the remote) |

## 7. Interview preparation status: Partially completed

The material is written ([`docs/interview.md`](docs/interview.md)). The student still has to practise the pitch aloud, rehearse the demo end to end (including `docker run` and a live LLM key if one will be shown), and be able to explain each topic in section G of that file without notes. Only the student can complete this.

## 8. Final remaining issues and manual actions

1. **Docker Desktop / disk space (manual).** Free disk space on C:, restart Docker Desktop, remove the audit images (`docker image rm kubecoach-day14:local kubecoach-day14:ctx`, `docker builder prune`), then build and run the image once.
2. **Check GitHub Actions** for the Day 14 commit (https://github.com/BhushanC23/GenAI/actions). Today's Dockerfile change (CPU-only PyTorch) has not been built in CI yet.
3. **Verify the Render and Hugging Face links** in a browser; remove them from the README and resume if they are not live.
4. **Live LLM path** (Groq or Gemini with a real key) was not exercised. `GEMINI_MODEL` defaults to `gemini-1.5-flash`; confirm the model name is still served before demonstrating Gemini.
5. **Known product limits** (see "Known Limitations" in `README.md`): 6 pages indexed, heuristic refusal rule, citations per retrieved chunk, extractive answers without an LLM key, no authentication or rate limiting, in-memory cache and agent memory.
6. **Workflow permission:** move `packages: write` to a separate publish job so test steps run with read-only permissions.
7. **Day 15** (final evaluation and presentation): pending; obtain the official task card and update `TRAINING_MASTER_PLAN.md`.
8. **Personal data in the repository:** `README.md` and `docs/` contain the student's registration number. Remove it if the repository is shared beyond the university.
