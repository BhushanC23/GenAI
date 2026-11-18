"""
tests/test_day09.py - Comprehensive Day 9 Agent & LangGraph Test Suite

29 deterministic tests (zero real API key required) covering:
- Quantity Converter (Tests 1-12): CPU, binary/decimal SI memory, comparisons, validation
- Hand-Written Agent Loop (Tests 13-18): tool selection, validation, errors, max iterations
- LangGraph Stateful Workflow (Tests 19-24): official interrupt/resume, MemorySaver, isolation, citations
- FastAPI Integration & Regression (Tests 25-29): POST /agent, POST /agent/approve, existing routes
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.agent_loop import run_agent_loop
from app.graph import (
    build_agent_graph,
    get_session_history,
    has_pending_approval,
    reset_agent_memory,
    resume_agent_approval,
    run_agent,
)
from app.main import app
from app.rag import Citation, RAGResult
from app.tools import (
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
    compare_k8s_quantities,
    execute_tool,
    get_tool_schema,
    k8s_quantity_converter,
    k8s_rag_search,
    validate_tool_call,
)


def _mock_rag_pod_result(**kwargs: Any) -> RAGResult:
    """Deterministic mock RAGResult for Pod documentation queries."""
    return RAGResult(
        question=kwargs.get("question", "What is a Pod?"),
        answer=(
            "A Pod is the smallest deployable unit of computing that you can create and manage in Kubernetes. "
            "Use `kubectl get pods` to list running pods."
        ),
        citations=[
            Citation(
                document_title="Pods",
                source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
                page="pods.md",
                chunk_id="doc:pods:chunk:001",
            )
        ],
        retrieved_chunks=[{"chunk_id": "doc:pods:chunk:001", "similarity": 0.91}],
        confidence="high",
        context_sufficient=True,
        provider="mock",
        model="deterministic-test",
    )


def _mock_rag_insufficient_result(**kwargs: Any) -> RAGResult:
    """Deterministic mock RAGResult for out-of-scope queries."""
    return RAGResult(
        question=kwargs.get("question", "How do I configure Istio mTLS?"),
        answer=(
            "I don't know based on the provided official Kubernetes documentation. "
            "The retrieved documents do not contain sufficient information to answer this question."
        ),
        citations=[],
        retrieved_chunks=[],
        confidence="low",
        context_sufficient=False,
        provider="kubecoach-guardrail",
        model="context-sufficiency-rule",
    )


# ===========================================================================
# Part 1: Quantity Converter Tests (Tests 1-12)
# ===========================================================================

class TestDay09QuantityConverter(unittest.TestCase):
    """Independent deterministic tests for k8s_quantity_converter (Decimal arithmetic)."""

    def test_01_cpu_500m_conversion(self) -> None:
        """1. 500m CPU converts accurately to 0.5 cores."""
        res = k8s_quantity_converter("500m")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "cpu")
        self.assertEqual(res["canonical_value"], "0.5 cores")
        self.assertEqual(res["representations"]["cores"], 0.5)
        self.assertEqual(res["representations"]["millicores"], "500m")

    def test_02_cpu_1000m_conversion(self) -> None:
        """2. 1000m CPU converts accurately to 1 core."""
        res = k8s_quantity_converter("1000m", target_unit="cores")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "cpu")
        self.assertEqual(res["canonical_value"], "1 core")
        self.assertEqual(res["representations"]["cores"], 1)
        self.assertEqual(res["target_conversion"], "1 core")

    def test_03_cpu_whole_conversion(self) -> None:
        """3. Whole CPU '2' converts accurately to 2 cores and 2000m."""
        res = k8s_quantity_converter("2", target_unit="m")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "cpu")
        self.assertEqual(res["representations"]["cores"], 2)
        self.assertEqual(res["representations"]["millicores"], "2000m")
        self.assertEqual(res["target_conversion"], "2000m")

    def test_04_memory_mi_conversion(self) -> None:
        """4. 512Mi memory converts accurately to 536,870,912 bytes and 0.5Gi."""
        res = k8s_quantity_converter("512Mi")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "memory")
        self.assertEqual(res["unit_system"], "binary_si")
        self.assertEqual(res["representations"]["bytes"], 536870912)
        self.assertEqual(res["representations"]["binary_si"]["Mi"], "512Mi")
        self.assertEqual(res["representations"]["binary_si"]["Gi"], "0.5Gi")

    def test_05_memory_gi_conversion(self) -> None:
        """5. 1Gi memory converts accurately to 1024 Mi and 1,073,741,824 bytes."""
        res = k8s_quantity_converter("1Gi", target_unit="Mi")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "memory")
        self.assertEqual(res["unit_system"], "binary_si")
        self.assertEqual(res["representations"]["bytes"], 1073741824)
        self.assertEqual(res["representations"]["binary_si"]["Mi"], "1024Mi")
        self.assertEqual(res["target_conversion"], "1024 Mi")

    def test_06_memory_decimal_g_conversion(self) -> None:
        """6. 1G decimal memory converts accurately to 1,000,000,000 bytes."""
        res = k8s_quantity_converter("1G", target_unit="bytes")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "memory")
        self.assertEqual(res["unit_system"], "decimal_si")
        self.assertEqual(res["representations"]["bytes"], 1000000000)
        self.assertEqual(res["target_conversion"], "1,000,000,000 bytes")

    def test_07_decimal_vs_binary_distinction(self) -> None:
        """7. Strictly distinguishes binary SI (1Gi) vs decimal SI (1G) and lowercase m vs uppercase M."""
        res_gi = k8s_quantity_converter("1Gi")
        res_g = k8s_quantity_converter("1G")
        self.assertEqual(res_gi["unit_system"], "binary_si")
        self.assertEqual(res_g["unit_system"], "decimal_si")
        self.assertEqual(
            res_gi["representations"]["bytes"] - res_g["representations"]["bytes"],
            73741824,
        )

        # Case sensitivity: 100m is CPU millicores, 100M is decimal Megabytes
        res_cpu = k8s_quantity_converter("100m")
        res_mem = k8s_quantity_converter("100M")
        self.assertEqual(res_cpu["resource_type"], "cpu")
        self.assertEqual(res_mem["resource_type"], "memory")
        self.assertEqual(res_mem["representations"]["bytes"], 100000000)

    def test_08_cpu_comparison(self) -> None:
        """8. Deterministic CPU comparison (less_than, equal, greater_than)."""
        cmp_lt = k8s_quantity_converter("500m", compare_to="1")
        self.assertTrue(cmp_lt["success"])
        self.assertEqual(cmp_lt["comparison"]["relation"], "less_than")
        self.assertEqual(cmp_lt["comparison"]["difference_cores"], -0.5)
        self.assertEqual(cmp_lt["comparison"]["ratio"], 0.5)

        cmp_eq = compare_k8s_quantities("1000m", "1")
        self.assertEqual(cmp_eq["relation"], "equal")
        self.assertEqual(cmp_eq["difference_cores"], 0)

        cmp_gt = compare_k8s_quantities("2", "1500m")
        self.assertEqual(cmp_gt["relation"], "greater_than")
        self.assertEqual(cmp_gt["difference_millicores"], 500)

    def test_09_memory_comparison(self) -> None:
        """9. Deterministic memory comparison including binary vs decimal and cross-type error."""
        cmp_bin_dec = k8s_quantity_converter("1Gi", compare_to="1G")
        self.assertTrue(cmp_bin_dec["success"])
        self.assertEqual(cmp_bin_dec["comparison"]["relation"], "greater_than")
        self.assertEqual(cmp_bin_dec["comparison"]["difference_bytes"], 73741824)

        cmp_eq = compare_k8s_quantities("1024Mi", "1Gi")
        self.assertEqual(cmp_eq["relation"], "equal")
        self.assertEqual(cmp_eq["difference_bytes"], 0)

        # Incompatible CPU vs Memory comparison fails with clear error
        mismatch = k8s_quantity_converter("500m", compare_to="512Mi")
        self.assertFalse(mismatch["success"])
        self.assertIn("incompatible resource types", mismatch["error"].lower())

    def test_10_invalid_input(self) -> None:
        """10. Negative, non-numeric, NaN, and extreme overflow inputs fail cleanly."""
        for bad in ("-500m", "-1Gi", "not_a_number", "NaN", "500m 200m", "999999999999cores"):
            res = k8s_quantity_converter(bad)
            self.assertFalse(res["success"], f"Expected failure for input: {bad}")
            self.assertIn("error", res)

    def test_11_unsupported_suffix(self) -> None:
        """11. Unsupported suffixes (Xi, foo, ZB) return clear validation errors."""
        for bad_suffix in ("100Xi", "500foo", "10ZB", "128mb"):
            res = k8s_quantity_converter(bad_suffix)
            self.assertFalse(res["success"], f"Expected failure for suffix: {bad_suffix}")
            self.assertIn("unsupported", res["error"].lower())

    def test_12_missing_input(self) -> None:
        """12. Missing, empty, or whitespace-only inputs fail safely."""
        for missing in ("", "   ", None):
            res = k8s_quantity_converter(missing)  # type: ignore[arg-type]
            self.assertFalse(res["success"])
            self.assertIn("non-empty string", res["error"].lower())


# ===========================================================================
# Part 2: Hand-Written Agent Loop Tests (Tests 13-18)
# ===========================================================================

class TestDay09AgentLoop(unittest.TestCase):
    """Deterministic unit tests for hand-written ReAct agent loop using mocked LLM planner."""

    @patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_pod_result)
    def test_13_agent_rag_tool_selection(self, _mock_rag: Any) -> None:
        """13. Agent selects k8s_rag_search, observes result, preserves citations, and traces steps."""
        def mock_planner(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not any(h.get("type") == "observation" for h in history):
                return {
                    "action": "tool_call",
                    "tool": "k8s_rag_search",
                    "arguments": {"query": question, "top_k": 2},
                    "thought": "Need official Kubernetes docs for Pods.",
                }
            obs = [h for h in history if h.get("type") == "observation"][-1]
            return {
                "action": "final_answer",
                "answer": obs["result"]["answer"],
                "thought": "Grounded documentation retrieved.",
            }

        result = run_agent_loop("What is a Pod?", planner_fn=mock_planner)
        self.assertTrue(result["success"])
        self.assertEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["tool"], "k8s_rag_search")
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["document_title"], "Pods")
        self.assertEqual(result["citations"][0]["page"], "pods.md")
        phases = [e["phase"] for e in result["execution_trace"]]
        self.assertIn("reason", phases)
        self.assertIn("select_tool", phases)
        self.assertIn("validate", phases)
        self.assertIn("execute", phases)
        self.assertIn("observe", phases)
        self.assertIn("final_answer", phases)

    def test_14_agent_quantity_converter_selection(self) -> None:
        """14. Agent selects k8s_quantity_converter and synthesizes deterministic Decimal output."""
        def mock_planner(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not any(h.get("type") == "observation" for h in history):
                return {
                    "action": "tool_call",
                    "tool": "k8s_quantity_converter",
                    "arguments": {"quantity": "1Gi", "compare_to": "1G"},
                    "thought": "Delegate binary vs decimal comparison to deterministic converter.",
                }
            obs = [h for h in history if h.get("type") == "observation"][-1]
            return {
                "action": "final_answer",
                "answer": obs["result"]["explanation"],
                "thought": "Comparison complete.",
            }

        result = run_agent_loop("Compare 1Gi and 1G", planner_fn=mock_planner)
        self.assertTrue(result["success"])
        self.assertEqual(result["tool_calls"][0]["tool"], "k8s_quantity_converter")
        self.assertIn("1,073,741,824 bytes", result["answer"])
        self.assertIn("73,741,824 bytes", result["answer"])

    def test_15_agent_invalid_tool_name(self) -> None:
        """15. Unregistered / hallucinated tool names are rejected before execution."""
        def mock_planner(_q: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not any(h.get("type") == "observation" for h in history):
                return {
                    "action": "tool_call",
                    "tool": "kubectl_delete_all_pods",
                    "arguments": {"namespace": "default"},
                    "thought": "Hallucinated unsafe tool.",
                }
            obs = [h for h in history if h.get("type") == "observation"][-1]
            return {
                "action": "final_answer",
                "answer": f"Safely blocked: {obs['result']['error']}",
                "thought": "Tool rejected by registry.",
            }

        result = run_agent_loop("Delete all pods", planner_fn=mock_planner)
        self.assertFalse(result["tool_calls"][0]["valid"])
        self.assertIn("not registered", result["answer"].lower())
        # Direct dispatcher check as well
        direct = execute_tool("non_existent_tool", {})
        self.assertFalse(direct["success"])
        self.assertIn("not registered", direct["error"].lower())

    def test_16_agent_invalid_tool_arguments(self) -> None:
        """16. Invalid, missing, or unexpected tool arguments are caught by schema validation."""
        # Missing required argument
        ok, err = validate_tool_call("k8s_quantity_converter", {})
        self.assertFalse(ok)
        self.assertIn("missing required", (err or "").lower())

        # Unexpected argument
        ok2, err2 = validate_tool_call("k8s_quantity_converter", {"quantity": "500m", "hack": True})
        self.assertFalse(ok2)
        self.assertIn("unexpected argument", (err2 or "").lower())

        # Wrong argument type inside agent loop
        def mock_planner(_q: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not any(h.get("type") == "observation" for h in history):
                return {
                    "action": "tool_call",
                    "tool": "k8s_rag_search",
                    "arguments": {"query": "Pods", "top_k": "three"},
                    "thought": "Invalid type for top_k.",
                }
            obs = [h for h in history if h.get("type") == "observation"][-1]
            return {
                "action": "final_answer",
                "answer": obs["result"]["error"],
                "thought": "Reporting validation error.",
            }

        result = run_agent_loop("What is a Pod?", planner_fn=mock_planner)
        self.assertFalse(result["tool_calls"][0]["valid"])
        self.assertIn("must be an integer", result["answer"].lower())

    @patch("app.tools.execute_rag_pipeline", side_effect=RuntimeError("ChromaDB offline"))
    def test_17_agent_tool_execution_failure(self, _mock_rag: Any) -> None:
        """17. Runtime errors inside tool execution are captured safely without crashing the loop."""
        def mock_planner(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
            if not any(h.get("type") == "observation" for h in history):
                return {
                    "action": "tool_call",
                    "tool": "k8s_rag_search",
                    "arguments": {"query": question, "top_k": 3},
                    "thought": "Query docs.",
                }
            obs = [h for h in history if h.get("type") == "observation"][-1]
            return {
                "action": "final_answer",
                "answer": f"Recovered cleanly: {obs['result']['error']}",
                "thought": "Reporting failure gracefully.",
            }

        result = run_agent_loop("What is a Pod?", planner_fn=mock_planner)
        self.assertFalse(result["observations"][0]["result"]["success"])
        self.assertIn("chromadb offline", result["answer"].lower())

    def test_18_agent_max_iteration_limit(self) -> None:
        """18. Infinite tool-calling planner terminates strictly at max_iterations."""
        call_counter = {"n": 0}

        def looping_planner(_q: str, _h: List[Dict[str, Any]]) -> Dict[str, Any]:
            call_counter["n"] += 1
            return {
                "action": "tool_call",
                "tool": "k8s_quantity_converter",
                "arguments": {"quantity": "500m"},
                "thought": "Keep looping to test safety guard.",
            }

        result = run_agent_loop("Loop forever", max_iterations=3, planner_fn=looping_planner)
        self.assertEqual(result["iterations"], 3)
        self.assertEqual(call_counter["n"], 3)
        self.assertTrue(result["stopped_by_limit"])
        self.assertIn("maximum iteration limit", result["answer"].lower())


# ===========================================================================
# Part 3: LangGraph Stateful Workflow Tests (Tests 19-24)
# ===========================================================================

class TestDay09LangGraphWorkflow(unittest.TestCase):
    """Tests verifying official LangGraph StateGraph, MemorySaver, and interrupt/resume."""

    def setUp(self) -> None:
        reset_agent_memory()

    def test_19_langgraph_approval_interrupt(self) -> None:
        """19. LangGraph pauses via interrupt() displaying proposed tool name and exact arguments."""
        graph = build_agent_graph()
        sid = "lg-interrupt-01"

        res = run_agent("Convert 512Mi memory to bytes", session_id=sid, graph=graph)
        self.assertTrue(res["approval_required"])
        self.assertEqual(res["approval_status"], "pending")
        self.assertTrue(has_pending_approval(sid, graph=graph))
        self.assertIsNotNone(res["pending_tool"])
        self.assertEqual(res["pending_tool"]["tool"], "k8s_quantity_converter")
        self.assertEqual(res["pending_tool"]["arguments"]["quantity"], "512Mi")
        self.assertEqual(res["tool_calls"], [])  # Not executed yet!
        self.assertIn("k8s_quantity_converter", res["answer"])

    def test_20_langgraph_approval_accepted(self) -> None:
        """20. Resuming paused LangGraph with approved=True executes tool and returns exact answer."""
        graph = build_agent_graph()
        sid = "lg-approve-01"

        paused = run_agent("Compare 1Gi and 1G memory", session_id=sid, graph=graph)
        self.assertTrue(paused["approval_required"])
        self.assertEqual(paused["pending_tool"]["tool"], "k8s_quantity_converter")

        completed = resume_agent_approval(session_id=sid, approved=True, graph=graph)
        self.assertFalse(completed["approval_required"])
        self.assertEqual(completed["approval_status"], "approved")
        self.assertFalse(has_pending_approval(sid, graph=graph))
        self.assertEqual(len(completed["tool_calls"]), 1)
        self.assertEqual(completed["tool_calls"][0]["tool"], "k8s_quantity_converter")
        self.assertIn("1,073,741,824 bytes", completed["answer"])
        self.assertIn("73,741,824 bytes", completed["answer"])

    @patch("app.graph.execute_tool")
    def test_21_langgraph_approval_rejected(self, mock_execute_tool: Any) -> None:
        """21. Resuming with approved=False skips tool execution completely and returns clear rejection."""
        graph = build_agent_graph()
        sid = "lg-reject-01"

        paused = run_agent("Convert 500m CPU to cores", session_id=sid, graph=graph)
        self.assertTrue(paused["approval_required"])

        rejected = resume_agent_approval(session_id=sid, approved=False, graph=graph)
        mock_execute_tool.assert_not_called()
        self.assertFalse(rejected["approval_required"])
        self.assertEqual(rejected["approval_status"], "rejected")
        self.assertEqual(rejected["tool_calls"], [])
        self.assertIn("rejected by the user", rejected["answer"].lower())
        self.assertIn("not executed", rejected["answer"].lower())

    @patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_pod_result)
    def test_22_langgraph_session_memory_persistence(self, _mock_rag: Any) -> None:
        """22. MemorySaver persists full multi-turn conversation history for a session_id."""
        graph = build_agent_graph()
        sid = "lg-memory-persist"

        r1 = run_agent("What is a Pod?", session_id=sid, graph=graph)
        self.assertFalse(r1["approval_required"])

        # Second turn on the same session_id
        r2 = run_agent("Convert 500m CPU to cores", session_id=sid, graph=graph)
        self.assertTrue(r2["approval_required"])
        r3 = resume_agent_approval(session_id=sid, approved=True, graph=graph)
        self.assertEqual(r3["approval_status"], "approved")

        history = get_session_history(sid, graph=graph)
        user_msgs = [m["content"] for m in history if m["role"] == "user"]
        asst_msgs = [m["content"] for m in history if m["role"] == "assistant"]
        self.assertEqual(user_msgs, ["What is a Pod?", "Convert 500m CPU to cores"])
        self.assertEqual(len(asst_msgs), 2)

    @patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_pod_result)
    def test_23_langgraph_session_isolation(self, _mock_rag: Any) -> None:
        """23. Separate session_ids remain strictly isolated in MemorySaver."""
        graph = build_agent_graph()

        # Session A asks a RAG question
        run_agent("What is a Pod?", session_id="session-alpha", graph=graph)
        # Session B pauses on quantity converter
        run_agent("Convert 1Gi to Mi", session_id="session-beta", graph=graph)

        hist_a = get_session_history("session-alpha", graph=graph)
        hist_b = get_session_history("session-beta", graph=graph)

        self.assertFalse(has_pending_approval("session-alpha", graph=graph))
        self.assertTrue(has_pending_approval("session-beta", graph=graph))
        self.assertEqual([m["content"] for m in hist_a if m["role"] == "user"], ["What is a Pod?"])
        self.assertEqual([m["content"] for m in hist_b if m["role"] == "user"], ["Convert 1Gi to Mi"])

    @patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_pod_result)
    def test_24_langgraph_citation_preservation(self, _mock_rag: Any) -> None:
        """24. RAG citations (title, URL, page, chunk_id) are preserved end-to-end; out-of-scope returns []."""
        graph = build_agent_graph()

        res = run_agent("What is a Pod and what command lists pods?", session_id="lg-cit-01", graph=graph)
        self.assertFalse(res["approval_required"])
        self.assertEqual(len(res["citations"]), 1)
        citation = res["citations"][0]
        self.assertEqual(citation["document_title"], "Pods")
        self.assertEqual(citation["source_url"], "https://kubernetes.io/docs/concepts/workloads/pods/")
        self.assertEqual(citation["page"], "pods.md")
        self.assertEqual(citation["chunk_id"], "doc:pods:chunk:001")

        # Insufficient context returns clear refusal and zero citations
        with patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_insufficient_result):
            refusal = run_agent("How do I configure Istio mTLS?", session_id="lg-cit-02", graph=graph)
            self.assertEqual(refusal["citations"], [])
            self.assertIn("don't know", refusal["answer"].lower())


# ===========================================================================
# Part 4: FastAPI Integration & Regression Checks (Tests 25-29)
# ===========================================================================

class TestDay09FastAPIIntegration(unittest.TestCase):
    """End-to-end API contract tests for POST /agent, POST /agent/approve, and existing routes."""

    def setUp(self) -> None:
        reset_agent_memory()
        self.client = TestClient(app)

    @patch("app.tools.execute_rag_pipeline", side_effect=_mock_rag_pod_result)
    def test_25_api_agent_rag_endpoint(self, _mock_rag: Any) -> None:
        """25. POST /agent answers RAG query with citations and execution_trace."""
        resp = self.client.post("/agent", json={"question": "What is a Pod?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["approval_required"])
        self.assertEqual(data["approval_status"], "not_required")
        self.assertEqual(len(data["citations"]), 1)
        self.assertGreaterEqual(len(data["execution_trace"]), 3)
        self.assertTrue(data["session_id"].startswith("sess-"))

    def test_26_api_agent_resume_via_agent_endpoint(self) -> None:
        """26. POST /agent supports pausing and resuming approval on the same endpoint."""
        r1 = self.client.post("/agent", json={"question": "Convert 500m CPU to cores"})
        self.assertEqual(r1.status_code, 200)
        d1 = r1.json()
        self.assertTrue(d1["approval_required"])
        self.assertEqual(d1["approval_status"], "pending")
        self.assertEqual(d1["pending_tool"]["tool"], "k8s_quantity_converter")
        sid = d1["session_id"]

        # Resume without even repeating the question
        r2 = self.client.post("/agent", json={"session_id": sid, "approved": True})
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertFalse(d2["approval_required"])
        self.assertEqual(d2["approval_status"], "approved")
        self.assertIn("0.5 cores", d2["answer"])

    def test_27_api_dedicated_approve_endpoint_and_conflict(self) -> None:
        """27. POST /agent/approve handles approve, reject, and HTTP 409 when no interrupt exists."""
        # Conflict when no pending approval exists
        conflict = self.client.post("/agent/approve", json={"session_id": "nonexistent", "approved": True})
        self.assertEqual(conflict.status_code, 409)

        # Trigger interrupt then reject via /agent/approve
        r1 = self.client.post("/agent", json={"question": "Convert 1Gi to Mi", "session_id": "api-rej-1"})
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.json()["approval_required"])

        r2 = self.client.post("/agent/approve", json={"session_id": "api-rej-1", "approved": False})
        self.assertEqual(r2.status_code, 200)
        d2 = r2.json()
        self.assertFalse(d2["approval_required"])
        self.assertEqual(d2["approval_status"], "rejected")
        self.assertEqual(d2["tool_calls"], [])

    def test_28_api_agent_validation_errors(self) -> None:
        """28. Empty/whitespace question without resume payload returns HTTP 422."""
        r1 = self.client.post("/agent", json={"question": "   "})
        self.assertEqual(r1.status_code, 422)

        r2 = self.client.post("/agent/approve", json={"session_id": "   ", "approved": True})
        self.assertEqual(r2.status_code, 422)

    def test_29_api_existing_routes_and_tool_schemas(self) -> None:
        """29. Verifies root links, existing endpoints (/health, /records, /search), and TOOL_SCHEMAS."""
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertEqual(root.json()["agent_url"], "/agent")
        self.assertEqual(root.json()["agent_approve_url"], "/agent/approve")

        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/records?limit=2").status_code, 200)
        self.assertEqual(self.client.get("/search?q=pod").status_code, 200)

        self.assertEqual(len(TOOL_SCHEMAS), 2)
        self.assertIsNotNone(get_tool_schema("k8s_rag_search"))
        self.assertIsNotNone(get_tool_schema("k8s_quantity_converter"))
        self.assertEqual(set(TOOL_REGISTRY.keys()), {"k8s_rag_search", "k8s_quantity_converter"})


if __name__ == "__main__":
    unittest.main()
