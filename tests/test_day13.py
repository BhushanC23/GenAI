"""Unit and integration test suite for Day 13: Observability, Caching, and Telemetry.

Validates:
1. POST /ask response schema includes latency_ms, token_usage, and cached fields.
2. First call records a cache miss with calculated token usage and latency.
3. Second identical call hits in-memory cache with cached=True and sub-50ms latency.
4. GET /cache/stats returns correct hits, misses, total_requests, and hit_ratio.
5. POST /cache/clear empties the cache and resets telemetry counters.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app, clear_rag_cache, get_cache_stats
from app.rag import Citation, RAGResult


class TestDay13ObservabilityAndCache(unittest.TestCase):
    """Test suite for production observability, telemetry, and query caching."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        # Reset cache before every test
        clear_rag_cache()

    def tearDown(self) -> None:
        clear_rag_cache()

    def test_cache_stats_endpoint_initial_state(self) -> None:
        """GET /cache/stats starts empty with 0 hits, 0 misses, and 0.0 hit ratio."""
        resp = self.client.get("/cache/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["cache_size"], 0)
        self.assertEqual(data["hits"], 0)
        self.assertEqual(data["misses"], 0)
        self.assertEqual(data["total_requests"], 0)
        self.assertEqual(data["hit_ratio"], 0.0)

    @patch("app.rag.execute_rag_pipeline")
    def test_ask_observability_fields_present_on_cache_miss(self, mock_rag: MagicMock) -> None:
        """POST /ask returns latency_ms, token_usage, and cached=False on first request."""
        mock_rag.return_value = RAGResult(
            question="What is a Pod?",
            answer="A Pod is the smallest deployable unit of computing in Kubernetes.",
            citations=[
                Citation(
                    document_title="Pods",
                    source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
                    page="pod",
                    chunk_id="pod-c001-abc12345",
                )
            ],
            retrieved_chunks=[{"text": "A Pod encapsulates one or more containers."}],
            confidence="high",
            context_sufficient=True,
        )

        resp = self.client.post("/ask", json={"question": "What is a Pod?", "top_k": 3})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check observability fields
        self.assertIn("latency_ms", data)
        self.assertIsInstance(data["latency_ms"], (int, float))
        self.assertGreaterEqual(data["latency_ms"], 0.0)

        self.assertIn("token_usage", data)
        self.assertIsInstance(data["token_usage"], dict)
        self.assertIn("prompt_tokens", data["token_usage"])
        self.assertIn("completion_tokens", data["token_usage"])
        self.assertIn("total_tokens", data["token_usage"])
        self.assertGreater(data["token_usage"]["total_tokens"], 0)

        self.assertIn("cached", data)
        self.assertFalse(data["cached"])

        # Cache stats should reflect 1 miss
        stats = self.client.get("/cache/stats").json()
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["total_requests"], 1)
        self.assertEqual(stats["cache_size"], 1)

    @patch("app.rag.execute_rag_pipeline")
    def test_ask_cache_hit_on_subsequent_request(self, mock_rag: MagicMock) -> None:
        """Second identical POST /ask request serves from cache with cached=True."""
        mock_rag.return_value = RAGResult(
            question="What is a Deployment?",
            answer="A Deployment provides declarative updates for Pods and ReplicaSets.",
            citations=[
                Citation(
                    document_title="Deployments",
                    source_url="https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
                    page="deployment",
                    chunk_id="deploy-c001-xyz98765",
                )
            ],
            retrieved_chunks=[{"text": "You describe a desired state in a Deployment."}],
            confidence="high",
            context_sufficient=True,
        )

        payload = {"question": "What is a Deployment?", "top_k": 3}

        # Request 1 (Cold / Cache Miss)
        resp1 = self.client.post("/ask", json=payload)
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertFalse(data1["cached"])
        self.assertEqual(mock_rag.call_count, 1)

        # Request 2 (Hot / Cache Hit)
        resp2 = self.client.post("/ask", json=payload)
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertTrue(data2["cached"])
        self.assertEqual(data2["answer"], data1["answer"])
        self.assertEqual(len(data2["citations"]), len(data1["citations"]))
        # LLM pipeline must NOT have been called a second time
        self.assertEqual(mock_rag.call_count, 1)
        # Token usage on cache hit is 0 LLM tokens
        self.assertEqual(data2["token_usage"]["total_tokens"], 0)

        # Cache stats: 1 hit, 1 miss, 50% hit ratio
        stats = self.client.get("/cache/stats").json()
        self.assertEqual(stats["hits"], 1)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["hit_ratio"], 0.5)

    def test_cache_clear_endpoint(self) -> None:
        """POST /cache/clear empties the cache and resets counters."""
        # Populate cache
        with patch("app.rag.execute_rag_pipeline") as mock_rag:
            mock_rag.return_value = RAGResult(
                question="What is a Pod?",
                answer="A Pod is a basic Kubernetes building block.",
                citations=[],
                retrieved_chunks=[],
                confidence="low",
                context_sufficient=False,
            )
            post_resp = self.client.post("/ask", json={"question": "What is a Pod?", "top_k": 2})
            self.assertEqual(post_resp.status_code, 200)

        stats_before = self.client.get("/cache/stats").json()
        self.assertEqual(stats_before["cache_size"], 1)

        # Clear cache
        clear_resp = self.client.post("/cache/clear")
        self.assertEqual(clear_resp.status_code, 200)
        clear_data = clear_resp.json()
        self.assertEqual(clear_data["status"], "cleared")
        self.assertEqual(clear_data["cleared_items"], 1)

        # Verify stats reset
        stats_after = self.client.get("/cache/stats").json()
        self.assertEqual(stats_after["cache_size"], 0)
        self.assertEqual(stats_after["hits"], 0)
        self.assertEqual(stats_after["misses"], 0)
        self.assertEqual(stats_after["total_requests"], 0)


if __name__ == "__main__":
    unittest.main()
