"""Automated unit tests for Day 6 KubeCoach implementations.

Verifies:
1. POST /chat endpoint schema, responses, and validation
2. LLM wrapper module (app/llm.py) provider handling and error types
3. Structured JSON extraction from markdown code fences
4. Prompt files existence and integrity (prompts/)
5. Preservation of all existing API endpoints (/health, /records, /search)
"""

import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    extract_structured_json,
    generate_chat_response,
    load_system_prompt,
)
from app.main import app


class TestDay06ChatEndpoint(unittest.TestCase):
    """Test POST /chat API endpoint behavior and validation."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_chat_endpoint_valid_question(self) -> None:
        payload = {
            "question": "What is a Pod and how do I inspect it?",
            "user_name": "Bhushan Chaturbhuj",
        }
        resp = self.client.post("/chat", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("answer", data)
        self.assertIn("confidence", data)
        self.assertIn("follow_up", data)
        self.assertIsInstance(data["answer"], str)
        self.assertGreater(len(data["answer"]), 10)
        self.assertIn(data["confidence"], ("high", "medium", "low"))

    def test_chat_endpoint_unanswerable_question(self) -> None:
        payload = {
            "question": "How do I configure an Istio Service Mesh with mTLS?",
            "user_name": "Student",
        }
        resp = self.client.post("/chat", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["confidence"], "low")
        self.assertIn("istio", data["answer"].lower())

    def test_chat_endpoint_missing_question_returns_422(self) -> None:
        resp = self.client.post("/chat", json={"user_name": "Student"})
        self.assertEqual(resp.status_code, 422)

    def test_chat_endpoint_short_question_returns_422(self) -> None:
        resp = self.client.post("/chat", json={"question": "a"})
        self.assertEqual(resp.status_code, 422)


class TestLLMModule(unittest.TestCase):
    """Test LLM provider wrapper functions and JSON parsing."""

    def test_load_system_prompt(self) -> None:
        prompt = load_system_prompt()
        self.assertIn("KubeCoach", prompt)
        self.assertIn("kubectl", prompt.lower())

    def test_extract_structured_json_with_fences(self) -> None:
        raw = """```json
{
  "answer": "A Pod is the smallest deployable unit.",
  "confidence": "high",
  "follow_up": "What is a Deployment?"
}
```"""
        result = extract_structured_json(raw)
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["answer"], "A Pod is the smallest deployable unit.")
        self.assertEqual(result["follow_up"], "What is a Deployment?")

    def test_extract_structured_json_fallback_on_plain_text(self) -> None:
        raw = "A Deployment is a controller that manages replica pods."
        result = extract_structured_json(raw)
        self.assertEqual(result["answer"], raw)
        self.assertIn("confidence", result)
        self.assertIn("follow_up", result)

    def test_generate_chat_response_mock(self) -> None:
        resp = generate_chat_response("What is a Service?", provider="mock")
        self.assertEqual(resp["confidence"], "high")
        self.assertIn("Service", resp["answer"])
        self.assertIn("kubectl", resp["answer"].lower())

    def test_error_classes_inheritance(self) -> None:
        self.assertTrue(issubclass(LLMTimeoutError, LLMError))
        self.assertTrue(issubclass(LLMRateLimitError, LLMError))
        self.assertTrue(issubclass(LLMAuthenticationError, LLMError))


class TestPromptFiles(unittest.TestCase):
    """Verify that prompt files and comparison evaluation exist."""

    def test_prompt_files_exist_and_non_empty(self) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        sys_prompt = base_dir / "prompts" / "system_prompt.md"
        explain_prompt = base_dir / "prompts" / "explain_concept.md"
        kubectl_prompt = base_dir / "prompts" / "kubectl_helper.md"
        compare_md = base_dir / "eval" / "prompt_compare.md"

        self.assertTrue(sys_prompt.is_file())
        self.assertTrue(explain_prompt.is_file())
        self.assertTrue(kubectl_prompt.is_file())
        self.assertTrue(compare_md.is_file())

        self.assertGreater(sys_prompt.stat().st_size, 50)
        self.assertGreater(explain_prompt.stat().st_size, 50)
        self.assertGreater(kubectl_prompt.stat().st_size, 50)
        self.assertGreater(compare_md.stat().st_size, 200)


class TestPreservedEndpoints(unittest.TestCase):
    """Ensure Day 4 endpoints have zero regression."""

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)

    def test_records(self) -> None:
        resp = self.client.get("/records?limit=3")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 3)

    def test_search(self) -> None:
        resp = self.client.get("/search?q=deployment")
        self.assertEqual(resp.status_code, 200)
        self.assertGreater(len(resp.json()), 0)


if __name__ == "__main__":
    unittest.main()
