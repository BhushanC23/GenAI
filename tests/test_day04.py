"""Automated tests for Day 4 KubeCoach implementations.

Verifies:
1. FastAPI endpoints: /health, /records, /records?limit=, /records/{id}, /search?q=, /questions
2. HTTP status codes and error responses (404, 422, 201)
3. Question persistence in data/questions.json
4. TF-IDF vectorization and Cosine Similarity ranking
5. Pandas exploratory data analysis execution
"""

import json
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from analysis.explore import explore_dataset
from app.main import QUESTIONS_FILE_PATH, app
from app.smart_search import smart_search


class TestFastAPIEndpoints(unittest.TestCase):
    """Test all FastAPI routes and request/response behavior."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        # Backup existing questions if any
        self.backup_questions = None
        if QUESTIONS_FILE_PATH.exists():
            self.backup_questions = QUESTIONS_FILE_PATH.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        # Restore backup questions
        if self.backup_questions is not None:
            QUESTIONS_FILE_PATH.write_text(self.backup_questions, encoding="utf-8")

    def test_root_endpoint(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("docs_url", data)

    def test_health_endpoint(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "KubeCoach API")
        self.assertGreaterEqual(data["records_count"], 18)

    def test_get_records_all(self) -> None:
        resp = self.client.get("/records")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 18)

    def test_get_records_with_limit(self) -> None:
        resp = self.client.get("/records?limit=5")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data), 5)

    def test_get_records_invalid_limit(self) -> None:
        resp = self.client.get("/records?limit=0")
        self.assertEqual(resp.status_code, 422)

    def test_get_record_valid_id(self) -> None:
        resp = self.client.get("/records/pod")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], "pod")
        self.assertEqual(data["page_title"], "Pods")
        self.assertIn("kubectl", data["key_kubectl_command"])

    def test_get_record_invalid_id_returns_404(self) -> None:
        resp = self.client.get("/records/non_existent_concept")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("detail", data)

    def test_search_endpoint_with_query(self) -> None:
        resp = self.client.get("/search?q=deployment")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertLessEqual(len(data), 3)
        # Top match should be Deployments
        self.assertEqual(data[0]["id"], "deployment")
        self.assertIn("score", data[0])
        self.assertGreater(data[0]["score"], 0.0)

    def test_search_endpoint_empty_query(self) -> None:
        resp = self.client.get("/search?q=")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_search_endpoint_whitespace_query(self) -> None:
        resp = self.client.get("/search?q=   ")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_submit_question_success(self) -> None:
        payload = {
            "question": "How does a StatefulSet differ from a Deployment?",
            "user_name": "Bhushan Chaturbhuj",
        }
        resp = self.client.post("/questions", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["status"], "saved")
        self.assertTrue(data["question_id"].startswith("q-"))
        self.assertEqual(data["question"], payload["question"])
        self.assertEqual(data["user_name"], payload["user_name"])

        # Check persistence in file
        self.assertTrue(QUESTIONS_FILE_PATH.exists())
        saved = json.loads(QUESTIONS_FILE_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(q["question_id"] == data["question_id"] for q in saved))

    def test_submit_question_invalid_validation(self) -> None:
        # Question too short (< 3 chars)
        payload = {"question": "hi"}
        resp = self.client.post("/questions", json=payload)
        self.assertEqual(resp.status_code, 422)

    def test_question_persistence_appends(self) -> None:
        QUESTIONS_FILE_PATH.write_text(json.dumps([]), encoding="utf-8")
        self.client.post("/questions", json={"question": "Question One"})
        self.client.post("/questions", json={"question": "Question Two"})

        saved = json.loads(QUESTIONS_FILE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0]["question"], "Question One")
        self.assertEqual(saved[1]["question"], "Question Two")


class TestSmartSearch(unittest.TestCase):
    """Test TF-IDF smart search logic, edge cases, and ranking."""

    def test_ranking_relevance(self) -> None:
        results = smart_search("network service exposing pods", top_k=3)
        self.assertGreater(len(results), 0)
        top_ids = [r["id"] for r in results]
        self.assertIn("service", top_ids)

    def test_empty_query_returns_empty(self) -> None:
        self.assertEqual(smart_search(""), [])
        self.assertEqual(smart_search("    "), [])

    def test_empty_dataset_handling(self) -> None:
        self.assertEqual(smart_search("pod", records=[]), [])

    def test_scores_are_positive_and_sorted(self) -> None:
        results = smart_search("kubectl secrets passwords", top_k=3)
        self.assertGreater(len(results), 0)
        scores = [r["score"] for r in results]
        self.assertTrue(all(s > 0 for s in scores))
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestPandasExplore(unittest.TestCase):
    """Test Pandas exploration script."""

    def test_explore_dataset_execution(self) -> None:
        df = explore_dataset()
        self.assertGreaterEqual(len(df), 18)
        self.assertIn("category", df.columns)
        self.assertIn("key_kubectl_command", df.columns)
        self.assertIn("workload", df["category"].values)


if __name__ == "__main__":
    unittest.main()

