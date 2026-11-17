"""Automated unit test suite for Day 8: RAG pipeline, citations, and POST /ask endpoint.

Verifies:
- End-to-end RAG pipeline execution on answerable queries.
- Accurate citation generation with title, page, and source URL.
- Out-of-scope refusal handling (Q6 Istio mTLS) returning 'I don't know' and 0 fake citations.
- Context sufficiency verification and boundary checks.
- Citation deduplication and formatting.
- FastAPI POST /ask endpoint contract, Pydantic validation (422), and responses.
- Backward compatibility regression across previous Day 1–7 endpoints.
"""

import unittest
from typing import Any, Dict, List

from fastapi.testclient import TestClient

from app.main import app
from app.rag import (
    Citation,
    RAGResult,
    build_citations,
    execute_rag_pipeline,
    format_context_for_prompt,
    is_context_sufficient,
    load_rag_prompt,
)
from app.vectorstore import get_vector_store


class TestRAGPipeline(unittest.TestCase):
    """Test suite for the core RAG pipeline in app/rag.py."""

    @classmethod
    def setUpClass(cls) -> None:
        store = get_vector_store()
        store.get_collection()

    def test_rag_system_prompt_loads(self) -> None:
        prompt = load_rag_prompt()
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 50)
        self.assertIn("KubeCoach", prompt)

    def test_build_citations_deduplication(self) -> None:
        chunks = [
            {
                "title": "Pods",
                "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
                "page": "pods.md",
                "chunk_id": "c1",
            },
            {
                "title": "Pods",
                "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
                "page": "pods.md",
                "chunk_id": "c2",
            },
            {
                "title": "Deployments",
                "source_url": "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
                "page": "deployment.md",
                "chunk_id": "c3",
            },
        ]
        citations = build_citations(chunks)
        self.assertEqual(len(citations), 2)
        titles = {c.document_title for c in citations}
        self.assertIn("Pods", titles)
        self.assertIn("Deployments", titles)

    def test_format_context_for_prompt(self) -> None:
        chunks = [
            {
                "title": "Pods",
                "page": "pods.md",
                "source_url": "https://k8s.io/pods",
                "text": "A Pod is a deployable unit.",
            }
        ]
        ctx_str = format_context_for_prompt(chunks)
        self.assertIn("[Context Block 1]", ctx_str)
        self.assertIn("Document Title: Pods", ctx_str)
        self.assertIn("A Pod is a deployable unit.", ctx_str)

    def test_context_sufficiency_empty_chunks(self) -> None:
        sufficient, reason = is_context_sufficient("What is a Pod?", [])
        self.assertFalse(sufficient)
        self.assertIn("No documentation chunks", reason)

    def test_context_sufficiency_low_similarity(self) -> None:
        chunks = [{"similarity": 0.20, "text": "Unrelated topic", "title": "Other"}]
        sufficient, reason = is_context_sufficient("What is a Pod?", chunks, min_similarity_threshold=0.55)
        self.assertFalse(sufficient)
        self.assertIn("below threshold", reason)

    def test_context_sufficiency_out_of_scope_tech(self) -> None:
        chunks = [
            {
                "similarity": 0.75,
                "text": "Kubernetes services provide cluster internal networking and load balancing.",
                "title": "Services",
            }
        ]
        sufficient, reason = is_context_sufficient(
            "How do I configure an Istio Service Mesh with mTLS?", chunks
        )
        self.assertFalse(sufficient)
        self.assertIn("istio", reason.lower())

    def test_context_sufficiency_valid(self) -> None:
        chunks = [
            {
                "similarity": 0.85,
                "text": "A Pod is the smallest deployable unit in Kubernetes representing a set of containers.",
                "title": "Pods",
            }
        ]
        sufficient, reason = is_context_sufficient("What is a Pod?", chunks)
        self.assertTrue(sufficient)

    def test_rag_pipeline_answerable_question(self) -> None:
        result = execute_rag_pipeline("What is a Pod?", top_k=2)
        self.assertIsInstance(result, RAGResult)
        self.assertTrue(result.context_sufficient)
        self.assertIn("pod", result.answer.lower())
        self.assertGreaterEqual(len(result.citations), 1)
        self.assertGreaterEqual(len(result.retrieved_chunks), 1)

        first_cite = result.citations[0]
        self.assertTrue(bool(first_cite.document_title))
        self.assertTrue(bool(first_cite.source_url))
        self.assertTrue(bool(first_cite.page))

    def test_rag_pipeline_unanswerable_q6_refusal(self) -> None:
        q6 = "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?"
        result = execute_rag_pipeline(q6, top_k=3)
        self.assertIsInstance(result, RAGResult)
        self.assertFalse(result.context_sufficient)
        self.assertIn("i don't know", result.answer.lower())
        # Zero fake citations for unanswerable queries
        self.assertEqual(len(result.citations), 0)
        self.assertEqual(result.confidence, "low")

    def test_rag_pipeline_empty_query(self) -> None:
        result = execute_rag_pipeline("", top_k=3)
        self.assertFalse(result.context_sufficient)
        self.assertIn("i don't know", result.answer.lower())
        self.assertEqual(len(result.citations), 0)


class TestAskEndpoint(unittest.TestCase):
    """Test suite for FastAPI POST /ask endpoint in app/main.py."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_root_endpoint_includes_ask_url(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("ask_url", data)
        self.assertEqual(data["ask_url"], "/ask")

    def test_ask_endpoint_success(self) -> None:
        payload = {"question": "What is a Pod and what command lists pods?", "top_k": 2}
        resp = self.client.post("/ask", json=payload)
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data["question"], payload["question"])
        self.assertIn("answer", data)
        self.assertIn("citations", data)
        self.assertIn("retrieved_chunks", data)
        self.assertIn("confidence", data)
        self.assertIn("context_sufficient", data)
        self.assertTrue(data["context_sufficient"])
        self.assertGreaterEqual(len(data["citations"]), 1)

        first_cite = data["citations"][0]
        self.assertIn("document_title", first_cite)
        self.assertIn("source_url", first_cite)
        self.assertIn("page", first_cite)

    def test_ask_endpoint_unanswerable_q6(self) -> None:
        payload = {
            "question": "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?",
            "top_k": 3,
        }
        resp = self.client.post("/ask", json=payload)
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertFalse(data["context_sufficient"])
        self.assertIn("i don't know", data["answer"].lower())
        self.assertEqual(len(data["citations"]), 0)
        self.assertEqual(data["confidence"], "low")

    def test_ask_endpoint_empty_question_returns_422(self) -> None:
        resp = self.client.post("/ask", json={"question": "   ", "top_k": 3})
        self.assertEqual(resp.status_code, 422)

    def test_ask_endpoint_invalid_top_k_returns_422(self) -> None:
        # top_k below 1
        resp_low = self.client.post("/ask", json={"question": "What is a Pod?", "top_k": 0})
        self.assertEqual(resp_low.status_code, 422)

        # top_k above 20
        resp_high = self.client.post("/ask", json={"question": "What is a Pod?", "top_k": 50})
        self.assertEqual(resp_high.status_code, 422)

    def test_preserved_previous_endpoints(self) -> None:
        # Day 4: /health
        h_resp = self.client.get("/health")
        self.assertEqual(h_resp.status_code, 200)
        self.assertEqual(h_resp.json()["status"], "ok")

        # Day 4: /records
        r_resp = self.client.get("/records?limit=2")
        self.assertEqual(r_resp.status_code, 200)
        self.assertEqual(len(r_resp.json()), 2)

        # Day 4: /search (TF-IDF)
        s_resp = self.client.get("/search?q=deployment")
        self.assertEqual(s_resp.status_code, 200)

        # Day 7: /search/semantic
        sem_resp = self.client.get("/search/semantic?q=deployment&limit=2")
        self.assertEqual(sem_resp.status_code, 200)
        self.assertIn("results", sem_resp.json())

        # Day 6: /chat
        chat_resp = self.client.post("/chat", json={"question": "What is a Pod?"})
        self.assertEqual(chat_resp.status_code, 200)
        self.assertIn("answer", chat_resp.json())


if __name__ == "__main__":
    unittest.main()
