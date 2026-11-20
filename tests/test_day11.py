"""tests/test_day11.py - Day 11 Comprehensive Testing & Quality Assurance Suite.

Covers end-to-end quality assurance across all KubeCoach components:
- Category A: Core Python functions, validation boundaries, and chunking edge cases
- Category B: FastAPI endpoint contracts, status codes, query limits, and 405 Method Not Allowed
- Category C: Ingestion pipeline resilience, mock network errors, and idempotence
- Category D: Search and retrieval edge cases (TF-IDF stop words and ChromaDB filtering)
- Category E: RAG pipeline grounding, citation authenticity, and refusal guardrails
- Category F: Deterministic quantity converter boundaries, tool schemas, and agent safety
- Category G: Streamlit UI client resilience, XSS protection, and feedback handling
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient
import requests

from app.models import Record, ValidationError, DataIngestionError
from app.records import load_records, load_record_models, get_by_id, search, count_by
from app.chunking import split_text, chunk_record, chunk_document
from app.ingest import clean_doc_text, parse_frontmatter_and_overview
from app.fetch import fetch_url
from app.smart_search import smart_search, build_corpus_document
from app.tools import (
    k8s_quantity_converter,
    k8s_rag_search,
    execute_tool,
    validate_tool_call,
    TOOL_SCHEMAS,
    TOOL_REGISTRY,
)
from app.agent_loop import run_agent_loop
from app.graph import run_agent, resume_agent_approval
from app.main import app
import app.main as main_module
from ui.api_client import check_health, ask_rag, approve_agent, submit_feedback
from ui.relationships import detect_mentioned_objects, extract_object_relationships, render_relationship_strip_html


# ------------------------------------------------------------------------------
# Category A: Core Python Functions & Data Validation QA
# ------------------------------------------------------------------------------
class TestDay11CoreFunctionsQA(unittest.TestCase):
    """QA tests for data models, validation boundaries, chunking, and text cleaning."""

    def test_01_record_model_validation_edge_cases(self) -> None:
        """Record model enforces mandatory fields, valid URLs, and generates valid slugs."""
        # Valid record creation
        rec = Record(
            id="",
            page_title="Horizontal Pod Autoscaler",
            category="workload",
            one_line_definition="Automatically scales the number of Pods in a workload.",
            key_kubectl_command="kubectl get hpa",
            limit_or_default="Default check interval is 15 seconds.",
            source_url="https://kubernetes.io/docs/concepts/workloads/autoscaling/",
        )
        self.assertEqual(rec.id, "horizontal-pod-autoscaler")
        self.assertEqual(rec.category, "workload")

        # Invalid URL schema raises ValidationError
        with self.assertRaises(ValidationError):
            Record(
                id="test-obj",
                page_title="Test",
                category="workload",
                one_line_definition="Test definition",
                key_kubectl_command="kubectl test",
                limit_or_default="None",
                source_url="ftp://invalid-url.com/docs",
            )

        # Missing mandatory string fields raise ValidationError
        with self.assertRaises(ValidationError):
            Record(
                id="test-obj",
                page_title="",
                category="workload",
                one_line_definition="Test definition",
                key_kubectl_command="kubectl test",
                limit_or_default="None",
                source_url="https://kubernetes.io/docs/test",
            )

    def test_02_record_loading_corrupted_file_resilience(self) -> None:
        """load_records safely falls back to seed records if records.json is missing or corrupt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_path = Path(tmpdir) / "corrupt_records.json"
            # Write invalid JSON syntax
            fake_path.write_text("{ unclosed json: missing brackets", encoding="utf-8")

            # Passing corrupt file path directly to load_records
            loaded = load_records(path=fake_path)
            self.assertIsInstance(loaded, list)
            self.assertGreaterEqual(len(loaded), 15)

    def test_03_chunking_edge_cases(self) -> None:
        """split_text handles empty strings, small texts, zero overlaps, and unicode cleanly."""
        # Empty text yields empty chunk list
        self.assertEqual(split_text(""), [])
        self.assertEqual(split_text("   "), [])

        # Text shorter than chunk size produces exactly 1 chunk
        short_text = "Kubernetes Pod is the atomic scheduling unit."
        chunks = split_text(short_text, chunk_size=200, chunk_overlap=20)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], short_text)

        # Text with unicode characters and special punctuation
        unicode_text = "Deployments: ☸ Pod-1 → Pod-2 — StatefulSet & ReplicaSet © 2026."
        u_chunks = split_text(unicode_text, chunk_size=50, chunk_overlap=10)
        self.assertGreaterEqual(len(u_chunks), 1)
        self.assertIn("☸", u_chunks[0])

    def test_04_doc_cleaning_hugo_and_comments_stripping(self) -> None:
        """clean_doc_text safely strips Hugo shortcodes and HTML comments while preserving content."""
        raw_markdown = (
            "<!-- This is a secret comment -->\n"
            "A {{< glossary_tooltip text=\"Pod\" term_id=\"pod\" >}} is the basic building block.\n"
            "```bash\nkubectl get pods\n```\n"
            "{{% alert title=\"Note\" %}}Read carefully{{% /alert %}}"
        )
        cleaned = clean_doc_text(raw_markdown)
        self.assertNotIn("<!--", cleaned)
        self.assertNotIn("secret comment", cleaned)
        self.assertNotIn("{{<", cleaned)
        self.assertIn("Pod", cleaned)
        self.assertIn("kubectl get pods", cleaned)


# ------------------------------------------------------------------------------
# Category B: FastAPI Endpoints Contract & Status Code QA
# ------------------------------------------------------------------------------
class TestDay11FastAPIEndpointsQA(unittest.TestCase):
    """Rigorous QA tests for all FastAPI REST endpoints, status codes, and input validation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_05_health_endpoint_contract(self) -> None:
        """GET /health returns HTTP 200 with status ok and integer records count."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertEqual(body.get("status"), "ok")
        self.assertIsInstance(body.get("records_count"), int)
        self.assertGreaterEqual(body.get("records_count"), 18)

    def test_06_records_endpoint_limits_and_pagination(self) -> None:
        """GET /records respects valid limits and rejects boundary violations with 422."""
        # Default returns all 18 records
        resp = self.client.get("/records")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.json()), 18)

        # Valid limit=5
        resp5 = self.client.get("/records?limit=5")
        self.assertEqual(resp5.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp5.json()), 5)

        # Boundary limit=1 (valid minimum)
        resp1 = self.client.get("/records?limit=1")
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp1.json()), 1)

        # Invalid limit=0 returns 422 Unprocessable
        resp0 = self.client.get("/records?limit=0")
        self.assertEqual(resp0.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Invalid limit=101 returns 422 Unprocessable
        resp101 = self.client.get("/records?limit=101")
        self.assertEqual(resp101.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

        # Negative limit returns 422
        resp_neg = self.client.get("/records?limit=-3")
        self.assertEqual(resp_neg.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_07_records_by_id_success_and_404_not_found(self) -> None:
        """GET /records/{id} returns 200 for known concept and 404 for unknown concept."""
        # Known concept
        resp_pod = self.client.get("/records/pod")
        self.assertEqual(resp_pod.status_code, status.HTTP_200_OK)
        data = resp_pod.json()
        self.assertEqual(data["id"], "pod")
        self.assertEqual(data["page_title"], "Pods")

        # Unknown concept returns 404
        resp_fake = self.client.get("/records/quantum-entangler-v3")
        self.assertEqual(resp_fake.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("not found", resp_fake.json()["detail"].lower())

    def test_08_search_endpoint_query_validation(self) -> None:
        """GET /search validates query length and returns structured ranked results."""
        # Valid search
        resp = self.client.get("/search?q=how+to+create+pods")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertIsInstance(body, list)
        self.assertGreaterEqual(len(body), 1)
        self.assertIn("page_title", body[0])
        self.assertIn("score", body[0])

        # Empty query string safely returns empty list with 200 OK
        resp_empty = self.client.get("/search?q=")
        self.assertEqual(resp_empty.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_empty.json(), [])

        # Non-matching query safely returns empty list or low scores
        resp_none = self.client.get("/search?q=xyznonexistentquery")
        self.assertEqual(resp_none.status_code, status.HTTP_200_OK)
        self.assertIsInstance(resp_none.json(), list)

    def test_09_semantic_search_endpoint_qa(self) -> None:
        """GET /search/semantic supports limit and category filtering with valid scores."""
        resp = self.client.get("/search/semantic?q=container+storage+volume&limit=3&category=storage")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertIn("results", body)
        for item in body["results"]:
            self.assertIn("chunk_id", item)
            self.assertIn("similarity", item)
            self.assertGreaterEqual(item["similarity"], 0.0)
            self.assertLessEqual(item["similarity"], 1.0)

    def test_10_endpoint_method_not_allowed_405(self) -> None:
        """HTTP method mismatches trigger HTTP 405 Method Not Allowed."""
        # POST to GET-only endpoint
        resp_post_health = self.client.post("/health", json={})
        self.assertEqual(resp_post_health.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # GET to POST-only endpoint
        resp_get_ask = self.client.get("/ask")
        self.assertEqual(resp_get_ask.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PUT to records
        resp_put = self.client.put("/records", json={})
        self.assertEqual(resp_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


# ------------------------------------------------------------------------------
# Category C: Ingestion Pipeline & Network Resilience QA
# ------------------------------------------------------------------------------
class TestDay11IngestionResilienceQA(unittest.TestCase):
    """QA tests verifying data ingestion handles network errors and malformed docs safely."""

    def test_11_fetch_url_connection_failure_isolation(self) -> None:
        """fetch_url logs and re-raises requests.ConnectionError so callers can handle network failures."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError("DNS failure")):
            with self.assertRaises(requests.exceptions.ConnectionError):
                fetch_url("https://kubernetes.io/docs/fake-page.md")

    def test_12_fetch_url_server_error_500(self) -> None:
        """fetch_url logs and re-raises HTTPError on server errors for explicit pipeline handling."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Internal Error")
        with patch("requests.get", return_value=mock_resp):
            with self.assertRaises(requests.exceptions.HTTPError):
                fetch_url("https://kubernetes.io/docs/error-page.md")

    def test_13_parse_frontmatter_missing_delimiters(self) -> None:
        """parse_frontmatter_and_overview safely parses files lacking standard YAML frontmatter."""
        text_without_fm = "## Overview\nA Pod represents a set of running containers."
        parsed = parse_frontmatter_and_overview(text_without_fm)
        self.assertIsInstance(parsed, dict)
        self.assertIn("overview", parsed)
        self.assertIn("Pod represents", parsed["overview"])


# ------------------------------------------------------------------------------
# Category D: Search & Retrieval Boundary QA
# ------------------------------------------------------------------------------
class TestDay11SearchAndRetrievalQA(unittest.TestCase):
    """QA tests for lexical TF-IDF search and dense ChromaDB retrieval boundaries."""

    def test_14_smart_search_pure_stopwords_behavior(self) -> None:
        """smart_search handles queries containing exclusively English stop words."""
        # Query with only stop words: 'what is the and or'
        results = smart_search("what is the and or", top_k=3)
        self.assertIsInstance(results, list)
        self.assertLessEqual(len(results), 3)

    def test_15_smart_search_gibberish_query(self) -> None:
        """smart_search with complete gibberish returns empty list or zero similarity."""
        results = smart_search("xyzqwwerty12345nonexistent", top_k=3)
        self.assertIsInstance(results, list)
        # Scores should be 0.0 or list should be empty
        for item in results:
            self.assertEqual(item.get("similarity_score", 0.0), 0.0)

    def test_16_corpus_structure_contains_all_fields(self) -> None:
        """build_corpus_document packages id, title, definition, command, and limit into indexable text."""
        records = load_records()
        self.assertGreaterEqual(len(records), 18)
        first_rec = records[0]
        searchable_text = build_corpus_document(first_rec)
        self.assertIn(first_rec["id"], searchable_text)
        self.assertIn(first_rec["page_title"], searchable_text)
        self.assertTrue(len(searchable_text) > 20)


# ------------------------------------------------------------------------------
# Category E: RAG Functionality, Grounding & Refusal QA
# ------------------------------------------------------------------------------
class TestDay11RAGFunctionalityQA(unittest.TestCase):
    """QA tests validating grounded generation, citation authenticity, and refusal guardrails."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_17_rag_answerable_question_citations_grounding(self) -> None:
        """POST /ask produces a grounded answer with verified official Kubernetes citations."""
        resp = self.client.post(
            "/ask",
            json={"question": "What is a Pod and how do I list running pods?", "top_k": 3},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertTrue(body["context_sufficient"])
        self.assertIn("pod", body["answer"].lower())
        self.assertGreaterEqual(len(body["citations"]), 1)

        # Check citation authenticity
        first_citation = body["citations"][0]
        self.assertTrue(bool(first_citation["source_url"]))
        self.assertTrue(len(first_citation["document_title"]) > 0)
        self.assertIn("pod", first_citation["document_title"].lower())

    def test_18_rag_out_of_scope_q6_honest_refusal(self) -> None:
        """POST /ask refuses out-of-scope query (Istio mTLS) with zero fake citations."""
        out_of_scope_q = (
            "How do I configure an Istio Service Mesh with Mutual TLS (mTLS) across multi-cluster deployments?"
        )
        resp = self.client.post("/ask", json={"question": out_of_scope_q, "top_k": 3})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        body = resp.json()
        self.assertFalse(body["context_sufficient"])
        self.assertIn("don't know", body["answer"].lower())
        self.assertEqual(body["citations"], [])

    def test_19_rag_empty_question_validation_error(self) -> None:
        """POST /ask with empty or whitespace-only question returns HTTP 422."""
        resp = self.client.post("/ask", json={"question": "   ", "top_k": 3})
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)


# ------------------------------------------------------------------------------
# Category F: Agent, Tools, Quantity Converter & HITL Safety QA
# ------------------------------------------------------------------------------
class TestDay11AgentAndToolsQA(unittest.TestCase):
    """QA tests for deterministic quantity converter arithmetic, tool schemas, and agent safety."""

    def test_20_quantity_converter_boundary_and_zero_values(self) -> None:
        """k8s_quantity_converter handles zero values and extreme boundaries deterministically."""
        # 0 cores and 0 millicores
        res_0m = k8s_quantity_converter("0m")
        self.assertTrue(res_0m["success"])
        self.assertEqual(res_0m["representations"]["cores"], 0)

        res_0core = k8s_quantity_converter("0", target_unit="m")
        self.assertTrue(res_0core["success"])
        self.assertEqual(res_0core["representations"]["cores"], 0)

        # 0 bytes and 0 memory
        res_0mi = k8s_quantity_converter("0Mi")
        self.assertTrue(res_0mi["success"])
        self.assertEqual(res_0mi["representations"]["bytes"], 0)

    def test_21_quantity_converter_equality_comparison(self) -> None:
        """k8s_quantity_converter correctly evaluates equality between different unit formats."""
        # 500m == 0.5 cores
        res_eq_cpu = k8s_quantity_converter("500m", compare_to="0.5")
        self.assertTrue(res_eq_cpu["success"])
        self.assertEqual(res_eq_cpu["comparison"]["relation"], "equal")
        self.assertEqual(res_eq_cpu["comparison"]["difference_cores"], 0)

        # 1024Mi == 1Gi
        res_eq_mem = k8s_quantity_converter("1024Mi", compare_to="1Gi")
        self.assertTrue(res_eq_mem["success"])
        self.assertEqual(res_eq_mem["comparison"]["relation"], "equal")
        self.assertEqual(res_eq_mem["comparison"]["difference_bytes"], 0)

    def test_22_quantity_converter_invalid_and_negative_inputs(self) -> None:
        """k8s_quantity_converter cleanly rejects negative quantities and invalid suffixes."""
        # Negative CPU
        res_neg = k8s_quantity_converter("-500m")
        self.assertFalse(res_neg["success"])
        self.assertIn("error", res_neg)

        # Invalid memory unit
        res_bad_unit = k8s_quantity_converter("128MegaBytes")
        self.assertFalse(res_bad_unit["success"])
        self.assertIn("error", res_bad_unit)

        # Gibberish string
        res_gibberish = k8s_quantity_converter("ten_gigabytes")
        self.assertFalse(res_gibberish["success"])
        self.assertIn("error", res_gibberish)

    def test_23_tool_registry_and_schema_enforcement(self) -> None:
        """Tool dispatcher rejects unknown tools and unvalidated payloads safely."""
        # Unknown tool returns error dict with success=False
        res = execute_tool("launch_kubernetes_missile", {})
        self.assertFalse(res["success"])
        self.assertIn("not registered", res["error"])

        # Validation error on missing quantity argument
        is_valid, err = validate_tool_call("k8s_quantity_converter", {})
        self.assertFalse(is_valid)
        self.assertIsNotNone(err)

        # Validation succeeds on valid payload
        is_valid, valid_err = validate_tool_call("k8s_quantity_converter", {"quantity": "500m"})
        self.assertTrue(is_valid)
        self.assertIsNone(valid_err)

    def test_24_agent_max_iterations_loop_prevention(self) -> None:
        """Hand-written run_agent_loop enforces max_iterations limit without infinite looping."""
        mock_planner = MagicMock()
        # Planner repeatedly requests tools without giving final answer
        mock_planner.return_value = {
            "thought": "I need more info",
            "action": "tool_call",
            "tool": "k8s_quantity_converter",
            "arguments": {"quantity": "1Gi"},
        }
        result = run_agent_loop("Infinite loop test query", max_iterations=3, planner_fn=mock_planner)
        self.assertEqual(result["iterations"], 3)
        self.assertTrue(result["stopped_by_limit"])
        self.assertIn("maximum iteration limit", result["answer"].lower())

    def test_25_langgraph_hitl_approval_isolation_and_rejection(self) -> None:
        """LangGraph workflow pauses for quantity comparison and handles human rejection cleanly."""
        sess_id = "test-day11-qa-sess"
        # Turn 1: Initiates quantity comparison requiring approval
        out_turn1 = run_agent("Compare 1Gi and 1G memory", session_id=sess_id)
        self.assertTrue(out_turn1["approval_required"])
        self.assertEqual(out_turn1["pending_tool"]["tool"], "k8s_quantity_converter")

        # Turn 2: Student rejects execution
        out_turn2 = resume_agent_approval(session_id=sess_id, approved=False)
        self.assertFalse(out_turn2["approval_required"])
        self.assertEqual(out_turn2["approval_status"], "rejected")
        self.assertIn("rejected", out_turn2["answer"].lower())
        self.assertEqual(out_turn2["tool_calls"], [])


# ------------------------------------------------------------------------------
# Category G: Streamlit UI Client, Relationships & Feedback QA
# ------------------------------------------------------------------------------
class TestDay11StreamlitUIQA(unittest.TestCase):
    """QA tests for UI API client error resilience, relationship strip rendering, and feedback."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_26_api_client_backend_health_resilience(self) -> None:
        """check_health handles timeouts and connection errors returning connected=False."""
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            health = check_health()
            self.assertFalse(health["connected"])
            self.assertIsNotNone(health["error"])

    def test_27_relationship_strip_case_insensitivity_and_structure(self) -> None:
        """detect_mentioned_objects detects lowercase, uppercase, and plural object names."""
        sample_text = "Students should scale DEPLOYMENTS and expose PODS via SERVICES."
        objs = detect_mentioned_objects(answer=sample_text)
        lower_objs = {o.lower() for o in objs}
        self.assertIn("deployment", lower_objs)
        self.assertIn("pods", lower_objs)
        self.assertIn("service", lower_objs)

        # Generates verified chain
        strip_data = extract_object_relationships(
            question="How to expose deployments?",
            answer=sample_text,
            context_sufficient=True,
        )
        self.assertIsNotNone(strip_data)
        self.assertEqual(strip_data["plain_text"], "Deployment → ReplicaSet → Pods ← Service")

        # Renders valid HTML container
        html = render_relationship_strip_html(strip_data)
        self.assertIn("kc-rel-container", html)
        self.assertIn("Deployment", html)
        self.assertIn("Pods", html)

    def test_28_feedback_conflict_duplicate_prevention(self) -> None:
        """POST /feedback rejects duplicate rating for same response_id with HTTP 409."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_fb = Path(tmpdir) / "test_feedback.json"
            with patch("app.main.FEEDBACK_FILE_PATH", tmp_fb):
                payload = {
                    "response_id": "resp-qa-001",
                    "session_id": "sess-qa-001",
                    "feedback": "up",
                    "question": "What is a Pod?",
                    "mode": "rag",
                }
                # First submission -> 201 Created
                r1 = self.client.post("/feedback", json=payload)
                self.assertEqual(r1.status_code, status.HTTP_201_CREATED)

                # Second submission with same response_id and session_id -> 409 Conflict
                r2 = self.client.post("/feedback", json=payload)
                self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)


if __name__ == "__main__":
    unittest.main()
