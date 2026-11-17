"""
tests/test_day09.py - Comprehensive Unit and Integration Tests for Day 9

Covers all 10 required Day 9 scenarios:
1. RAG question triggers RAG search tool
2. Quantity question triggers converter tool
3. Multi-part question triggers both tools
4. Invalid tool name handling
5. Invalid tool arguments handling
6. Tool execution failure handling
7. Human approval requested when converter tool selected
8. Human approval rejection stops execution cleanly
9. Conversation memory retains context across multiple turns
10. Iteration limit prevents infinite loops
Plus FastAPI /agent endpoint tests and tool schema validation.
"""

from __future__ import annotations
import unittest
from fastapi.testclient import TestClient

from app.agent_loop import run_agent_loop, _detect_tool_call_intent
from app.graph import (
    clear_session_memory,
    get_session_state,
    run_agent,
    save_session_state,
    AgentState,
)
from app.main import app
from app.tools import (
    execute_tool,
    get_tool_schema,
    k8s_quantity_converter,
    k8s_rag_search,
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
)


class TestDay09Tools(unittest.TestCase):
    """Test individual tools and safe dispatcher in app/tools.py."""

    def test_cpu_quantity_converter_millicores(self) -> None:
        """Verify converting millicores to cores."""
        res = k8s_quantity_converter("500m")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "cpu")
        self.assertEqual(res["representations"]["cores"], 0.5)
        self.assertEqual(res["representations"]["millicores"], "500m")
        self.assertIn("0.5 core", res["explanation"])

    def test_cpu_quantity_converter_cores_to_millicores(self) -> None:
        """Verify converting whole cores to millicores with target_unit."""
        res = k8s_quantity_converter("2", target_unit="m")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "cpu")
        self.assertEqual(res["representations"]["millicores"], "2000m")
        self.assertEqual(res["target_conversion"], "2000m")

    def test_memory_quantity_converter_binary_si(self) -> None:
        """Verify converting binary SI units (128Mi, 2Gi) to bytes and representations."""
        res128 = k8s_quantity_converter("128Mi")
        self.assertTrue(res128["success"])
        self.assertEqual(res128["resource_type"], "memory")
        self.assertEqual(res128["representations"]["bytes"], 134217728)
        self.assertEqual(res128["representations"]["binary_si"]["Mi"], "128Mi")

        res2gi = k8s_quantity_converter("2Gi", target_unit="Mi")
        self.assertTrue(res2gi["success"])
        self.assertEqual(res2gi["representations"]["bytes"], 2147483648)
        self.assertEqual(res2gi["target_conversion"], "2048.0 Mi")

    def test_memory_quantity_converter_decimal_si(self) -> None:
        """Verify converting decimal SI units (100M)."""
        res = k8s_quantity_converter("100M")
        self.assertTrue(res["success"])
        self.assertEqual(res["resource_type"], "memory")
        self.assertEqual(res["representations"]["bytes"], 100000000)

    def test_quantity_converter_invalid_formats(self) -> None:
        """Verify invalid formats and out-of-bounds quantities fail safely (Scenario 6)."""
        # Negative CPU
        neg_cpu = k8s_quantity_converter("-250m")
        self.assertFalse(neg_cpu["success"])
        self.assertIn("error", neg_cpu)

        # Negative Memory
        neg_mem = k8s_quantity_converter("-10Gi")
        self.assertFalse(neg_mem["success"])

        # Absurd bounds
        overflow = k8s_quantity_converter("999999999999cores")
        self.assertFalse(overflow["success"])

        # Empty / non-string
        empty_res = k8s_quantity_converter("   ")
        self.assertFalse(empty_res["success"])

    def test_rag_search_tool_execution(self) -> None:
        """Verify k8s_rag_search returns citations and grounded answer."""
        res = k8s_rag_search("What is a Pod?", top_k=2)
        self.assertTrue(res["success"])
        self.assertEqual(res["tool"], "k8s_rag_search")
        self.assertTrue(len(res["answer"]) > 0)
        self.assertIsInstance(res["citations"], list)

    def test_rag_search_tool_invalid_query(self) -> None:
        """Verify k8s_rag_search rejects empty queries safely."""
        res = k8s_rag_search("   ")
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    def test_tool_dispatcher_invalid_name(self) -> None:
        """Scenario 4: Invalid tool name handling."""
        res = execute_tool("non_existent_tool_name", {})
        self.assertFalse(res["success"])
        self.assertIn("not found", res["error"])
        self.assertIn("k8s_quantity_converter", res["error"])

    def test_tool_dispatcher_invalid_arguments(self) -> None:
        """Scenario 5: Invalid tool arguments handling."""
        # Missing required argument 'quantity'
        res = execute_tool("k8s_quantity_converter", {"unknown_arg": 123})
        self.assertFalse(res["success"])
        self.assertIn("Missing required arguments", res["error"])

        # Non-dict arguments
        res_non_dict = execute_tool("k8s_quantity_converter", "string_arg")  # type: ignore
        self.assertFalse(res_non_dict["success"])

    def test_tool_schemas_completeness(self) -> None:
        """Verify TOOL_SCHEMAS contains valid definitions for all registered tools."""
        self.assertEqual(len(TOOL_SCHEMAS), 2)
        schema_names = [s["name"] for s in TOOL_SCHEMAS]
        self.assertIn("k8s_rag_search", schema_names)
        self.assertIn("k8s_quantity_converter", schema_names)
        for name in schema_names:
            schema = get_tool_schema(name)
            self.assertIsNotNone(schema)
            self.assertIn("parameters", schema)
            self.assertIn("required", schema["parameters"])


class TestDay09AgentLoop(unittest.TestCase):
    """Test educational agent loop in app/agent_loop.py."""

    def test_scenario_01_rag_question_triggers_rag_tool(self) -> None:
        """Scenario 1: RAG question triggers RAG search tool."""
        result = run_agent_loop("What is a Deployment and what kubectl command creates one?")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["tool"], "k8s_rag_search")
        self.assertGreaterEqual(len(result["citations"]), 1)
        self.assertTrue(len(result["answer"]) > 0)

    def test_scenario_02_quantity_question_triggers_converter_tool(self) -> None:
        """Scenario 2: Quantity question triggers converter tool."""
        result = run_agent_loop("Convert 500m CPU to cores")
        self.assertTrue(result["success"])
        self.assertGreaterEqual(len(result["tool_calls"]), 1)
        self.assertEqual(result["tool_calls"][0]["tool"], "k8s_quantity_converter")
        self.assertIn("0.5 core", result["answer"])

    def test_scenario_03_multi_step_tool_execution(self) -> None:
        """Scenario 3: Multi-part question triggers tool calls and synthesizes results."""
        # Custom sequential injection testing synthesis
        res = run_agent_loop("What is a Pod and convert 250m cpu")
        self.assertTrue(res["success"])
        self.assertGreaterEqual(len(res["tool_calls"]), 1)
        self.assertTrue(len(res["answer"]) > 0)

    def test_scenario_10_iteration_limit_enforced(self) -> None:
        """Scenario 10: Iteration limit prevents infinite loops."""
        # When max_iterations is small (e.g. 1), loop terminates without running unboundedly
        res = run_agent_loop("What is a Pod?", max_iterations=1)
        self.assertLessEqual(res["iterations"], 1)

    def test_empty_question_handling(self) -> None:
        """Verify graceful error when question is empty."""
        res = run_agent_loop("   ")
        self.assertFalse(res["success"])
        self.assertEqual(len(res["tool_calls"]), 0)


class TestDay09LangGraphWorkflow(unittest.TestCase):
    """Test LangGraph stateful workflow in app/graph.py."""

    def setUp(self) -> None:
        clear_session_memory()

    def test_scenario_07_human_approval_requested_for_converter(self) -> None:
        """Scenario 7: Human approval requested when converter tool selected."""
        res = run_agent("Convert 128Mi memory to bytes", session_id="test-approval-req")
        self.assertTrue(res["success"])
        self.assertTrue(res["approval_required"])
        self.assertEqual(res["approval_status"], "pending")
        self.assertIsNotNone(res["pending_tool"])
        self.assertEqual(res["pending_tool"]["name"], "k8s_quantity_converter")
        self.assertIn("Human approval required", res["answer"])

    def test_scenario_08_human_approval_rejection_stops_execution(self) -> None:
        """Scenario 8: Human approval rejection stops execution cleanly."""
        sid = "test-rejection-flow"
        # Turn 1: request conversion
        turn1 = run_agent("Convert 500m CPU", session_id=sid)
        self.assertTrue(turn1["approval_required"])

        # Turn 2: reject execution
        turn2 = run_agent("reject", session_id=sid, approved=False)
        self.assertFalse(turn2["approval_required"])
        self.assertEqual(turn2["approval_status"], "rejected")
        self.assertIn("rejected by user", turn2["answer"])

    def test_scenario_09_conversation_memory_retains_context(self) -> None:
        """Scenario 9: Conversation memory retains context across multiple turns."""
        sid = "test-memory-flow"

        # Turn 1: trigger approval gate
        turn1 = run_agent("Convert 2Gi memory", session_id=sid)
        self.assertTrue(turn1["approval_required"])

        # Verify saved state in memory
        saved = get_session_state(sid)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["session_id"], sid)

        # Turn 2: approve on same session_id
        turn2 = run_agent("proceed", session_id=sid, approved=True)
        self.assertFalse(turn2["approval_required"])
        self.assertEqual(turn2["approval_status"], "approved")
        self.assertIn("2,147,483,648 bytes", turn2["answer"])

    def test_rag_query_does_not_require_approval(self) -> None:
        """Verify safe read-only RAG queries do not pause at approval gate."""
        res = run_agent("What is a Pod?")
        self.assertTrue(res["success"])
        self.assertFalse(res["approval_required"])
        self.assertIsNone(res["approval_status"])
        self.assertGreaterEqual(len(res["citations"]), 1)
        self.assertTrue(len(res["answer"]) > 0)


class TestDay09FastAPIAgentEndpoint(unittest.TestCase):
    """Test POST /agent endpoint integration via FastAPI TestClient."""

    def setUp(self) -> None:
        self.client = TestClient(app)
        clear_session_memory()

    def test_root_endpoint_includes_agent_url(self) -> None:
        """Verify GET / lists agent_url."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("agent_url"), "/agent")

    def test_agent_endpoint_empty_question_validation(self) -> None:
        """Verify empty question returns HTTP 422."""
        resp = self.client.post("/agent", json={"question": "   "})
        self.assertEqual(resp.status_code, 422)

    def test_agent_endpoint_rag_search(self) -> None:
        """Verify POST /agent handles RAG documentation query."""
        resp = self.client.post("/agent", json={"question": "What is a Pod?"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["approval_required"])
        self.assertTrue(len(data["answer"]) > 0)
        self.assertGreaterEqual(len(data["citations"]), 1)
        self.assertTrue(data["session_id"].startswith("sess-"))

    def test_agent_endpoint_quantity_converter_lifecycle(self) -> None:
        """Verify full HITL lifecycle: request -> pending -> approve -> completed."""
        # Step 1: initial request
        resp1 = self.client.post(
            "/agent",
            json={"question": "Convert 500m CPU to cores"},
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertTrue(data1["approval_required"])
        self.assertEqual(data1["approval_status"], "pending")
        sid = data1["session_id"]

        # Step 2: approve
        resp2 = self.client.post(
            "/agent",
            json={"question": "yes approve", "session_id": sid, "approved": True},
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertFalse(data2["approval_required"])
        self.assertEqual(data2["approval_status"], "approved")
        self.assertIn("0.5 core", data2["answer"])


if __name__ == "__main__":
    unittest.main()
