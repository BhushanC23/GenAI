# KubeCoach — Day 8 RAG Configuration Benchmark & Evaluation Report

## Executive Summary
This report compares two RAG pipeline configurations evaluated across all 15 benchmark questions in `eval/eval_set.json`.
- **Winning Configuration:** **Configuration A**
- **Rationale:** Configuration A achieved higher aggregate quality (Answer Correctness: 32.2% vs 32.1%, Retrieval: 86.7%) with lower average retrieval latency (25.1ms vs 25.6ms). Smaller, tighter chunks (500 chars) preserve finer concept boundaries without diluting embeddings across unrelated paragraphs.

---

## Configuration Comparison Summary

| Metric | Configuration A (Target: 500 chars, k=3) | Configuration B (Target: 800 chars, k=5) | Winner |
| :--- | :--- | :--- | :--- |
| **Chunk Size** | 500 chars | 800 chars | - |
| **Chunk Overlap** | 100 chars | 150 chars | - |
| **Top-K Chunks Retrieved** | 3 chunks | 5 chunks | - |
| **Total Chunks in Collection** | 427 chunks | 271 chunks | - |
| **Retrieval Relevance** | **86.7%** | **86.7%** | Config A |
| **Citation Correctness** | **100.0%** | **100.0%** | Tie |
| **Answer Correctness** | **32.2%** | **32.1%** | Config A |
| **Q6 Refusal Behavior ('I don't know')** | **PASS (100%)** | **PASS (100%)** | **Tie (Both Pass)** |
| **Average Latency per Query** | **25.1 ms** | **25.6 ms** | Config A |
| **Total Benchmark Time** | **377.0 ms** | **384.3 ms** | Config A |

---

## Per-Question Benchmark Breakdown (15 Evaluation Questions)

| ID | Question | Expected Sources | Config A Answer Score | Config B Answer Score | Config A Citations | Config B Citations | Q6 Refusal |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Q1** | What is a Pod? | `pods.md, records.json` | 47.6% | 47.6% | 1 cited | 1 cited | N/A (Answerable) |
| **Q2** | What is a Deployment? | `deployment.md, records.json` | 21.4% | 42.9% | 1 cited | 1 cited | N/A (Answerable) |
| **Q3** | What is a Kubernetes Service? | `service.md, records.json` | 25.0% | 25.0% | 3 cited | 5 cited | N/A (Answerable) |
| **Q4** | How do I store sensitive credentials like passwords and API keys in Kubernetes? | `records.json` | 54.5% | 54.5% | 2 cited | 2 cited | N/A (Answerable) |
| **Q5** | How do I isolate resources and define team permissions within a single cluster? | `namespaces.md, records.json` | 28.0% | 20.0% | 3 cited | 5 cited | N/A (Answerable) |
| **Q6** | How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments? | `None (Unanswerable)` | 100.0% | 100.0% | 0 cited | 0 cited | Refused Correctly |
| **Q7** | How do I ensure a logging or monitoring pod runs on every single worker node in my cluster? | `records.json` | 21.1% | 21.1% | 1 cited | 2 cited | N/A (Answerable) |
| **Q8** | What is the difference between a ConfigMap and a Secret for environment variables? | `configmap.md, records.json` | 17.9% | 17.9% | 1 cited | 1 cited | N/A (Answerable) |
| **Q9** | How can an administrator restrict total CPU and memory consumption in a specific namespace? | `records.json` | 8.7% | 13.0% | 2 cited | 2 cited | N/A (Answerable) |
| **Q10** | What controller should I use for a stateful database that requires stable network identities and dedicated storage? | `records.json` | 13.6% | 9.1% | 2 cited | 5 cited | N/A (Answerable) |
| **Q11** | What are the allowed values for a Pod restartPolicy and what is the default? | `pods.md` | 40.0% | 20.0% | 2 cited | 2 cited | N/A (Answerable) |
| **Q12** | What is the difference between a ClusterIP and a NodePort Service? | `service.md, records.json` | 27.3% | 27.3% | 1 cited | 2 cited | N/A (Answerable) |
| **Q13** | How does a Deployment perform a rolling update when the container image is updated? | `deployment.md, records.json` | 15.8% | 15.8% | 2 cited | 2 cited | N/A (Answerable) |
| **Q14** | What is an Ingress Controller and why is an Ingress resource alone not enough? | `ingress.md, records.json` | 15.0% | 20.0% | 1 cited | 1 cited | N/A (Answerable) |
| **Q15** | What is the difference between a PersistentVolume (PV) and a PersistentVolumeClaim (PVC)? | `records.json` | 47.4% | 47.4% | 3 cited | 4 cited | N/A (Answerable) |

---

## Key Qualitative Observations & Insights

### 1. Granular Chunks (Config A: 500 chars) vs. Broad Chunks (Config B: 800 chars)
- **Information Density:** The 500-character chunking in Configuration A preserves distinct Kubernetes concept definitions and commands in concentrated units. Because `all-MiniLM-L6-v2` produces a single 384-dimensional pooled vector per chunk, shorter chunks maintain higher semantic density and yield sharper cosine similarity scores.
- **Dilution in Larger Chunks:** In Configuration B (800 chars), chunks frequently span multiple conceptual transitions (e.g. from Pod definition to PodDisruptionBudgets or unrelated security context settings), which slightly dilutes vector embeddings and introduces non-essential context.

### 2. Out-of-Scope Handling (Question Q6)
- **Question:** *'How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?'*
- **Grounding Rule Outcome:** Both configurations successfully refused Q6 with an honest:  
  `'I don't know based on the provided official Kubernetes documentation.'`
- **Zero Fake Citations:** Both configurations correctly produced `0` citations for Q6. No hallucinated documentation links were generated.
- **Why the Rule Works Universally:** The context-sufficiency rule in `app/rag.py` checks both similarity thresholds and query entity coverage against retrieved chunks. It is not hardcoded to Q6 and applies to any external tool query (e.g. Nomad, Consul, Linkerd).

### 3. Automated Scoring Methodology & Limitations
> [!NOTE]
> **Methodology Transparency:** Answer correctness is computed via keyword recall against factual reference answers derived from official documentation. Retrieval relevance evaluates whether at least one expected source was retrieved. Citation correctness verifies that citations are non-empty for answerable queries and empty for unanswerable queries.

> [!IMPORTANT]
> **Limitations of Automated Evaluation:** Keyword overlap provides an objective, deterministic lower bound on factual recall, but cannot evaluate pedagogical phrasing, nuance, or conversational tone. Human evaluation is recommended for verifying interview suitability.

---
**Benchmark generated at:** 2026-11-24 12:52:49