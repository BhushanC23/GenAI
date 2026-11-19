"""
tests/test_day10.py - Comprehensive Day 10 Streamlit UI, Integration & Feedback Tests

Covers all required Day 10 scenarios with mocked HTTP and isolated temp storage:
1. Application starts cleanly (Streamlit AppTest)
2. Backend health check (connected & disconnected)
3. Successful /ask request
4. Successful /agent request
5. API connection failure & timeout handling
6. Invalid backend response (non-JSON / missing fields)
7. Citation rendering (clickable links & missing-source notice)
8. Kubernetes Object Relationship Strip mapping & HTML rendering
9. Persistent feedback submission & duplicate prevention (POST /feedback & GET /feedback)
10. Agent approval & rejection flow
11. Session history & New Chat reset
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

import app.main as main_module
from ui.api_client import (
    BackendAPIError,
    approve_agent,
    ask_rag,
    check_health,
    get_api_base_url,
    run_agent,
    submit_feedback,
)
from ui.app import (
    STARTER_QUESTIONS,
    execute_user_query,
    format_citations_html,
    initialize_session_state,
    reset_chat_session,
)
from ui.relationships import (
    detect_mentioned_objects,
    extract_object_relationships,
    render_relationship_strip_html,
)


def _mock_response(status_code: int = 200, json_data: Any = None, bad_json: bool = False) -> MagicMock:
    """Create a mock `requests.Response` object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason = "OK" if status_code < 400 else "Error"
    if bad_json:
        resp.json.side_effect = ValueError("No JSON object could be decoded")
    else:
        resp.json.return_value = json_data
    return resp


class TestDay10BackendClient(unittest.TestCase):
    """Tests for ui/api_client.py HTTP communication and error handling."""

    def test_01_api_base_url_env_and_default(self) -> None:
        """Reads API_BASE_URL from environment and falls back safely to localhost:8000."""
        with patch.dict("os.environ", {"API_BASE_URL": "https://api.kubecoach.dev/"}):
            self.assertEqual(get_api_base_url(), "https://api.kubecoach.dev")
        with patch.dict("os.environ", {"API_BASE_URL": ""}):
            self.assertEqual(get_api_base_url(), "http://127.0.0.1:8000")

    @patch("ui.api_client.requests.request")
    def test_02_backend_health_check_connected_and_disconnected(self, mock_req: MagicMock) -> None:
        """Reports connected ONLY when /health returns HTTP 200 and status=='ok'."""
        mock_req.return_value = _mock_response(
            200,
            {"status": "ok", "app": "KubeCoach API", "version": "1.0.0", "records_count": 18},
        )
        ok_status = check_health(base_url="http://127.0.0.1:8000")
        self.assertTrue(ok_status["connected"])
        self.assertEqual(ok_status["records_count"], 18)

        # Connection failure must report connected=False
        mock_req.side_effect = requests.exceptions.ConnectionError("Connection refused")
        err_status = check_health(base_url="http://127.0.0.1:8000")
        self.assertFalse(err_status["connected"])
        self.assertIn("Unable to reach KubeCoach backend", err_status["error"])

    @patch("ui.api_client.requests.request")
    def test_03_successful_ask_request(self, mock_req: MagicMock) -> None:
        """Calls POST /ask cleanly and preserves grounded answer and citations."""
        mock_req.return_value = _mock_response(
            200,
            {
                "question": "What is a Pod?",
                "answer": "A Pod is the smallest deployable compute unit in Kubernetes.",
                "citations": [
                    {
                        "document_title": "Pods",
                        "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
                        "page": "pods.md",
                    }
                ],
                "retrieved_chunks": [],
                "confidence": "high",
                "context_sufficient": True,
            },
        )
        data = ask_rag("What is a Pod?", base_url="http://127.0.0.1:8000")
        self.assertIn("smallest deployable", data["answer"])
        self.assertEqual(len(data["citations"]), 1)
        mock_req.assert_called_once()
        self.assertTrue(mock_req.call_args.kwargs["url"].endswith("/ask"))

    @patch("ui.api_client.requests.request")
    def test_04_successful_agent_request(self, mock_req: MagicMock) -> None:
        """Calls POST /agent preserving session_id and returning tool_calls/approval fields."""
        mock_req.return_value = _mock_response(
            200,
            {
                "question": "Compare 1Gi and 1G",
                "answer": "Human approval required before executing 'k8s_quantity_converter'.",
                "tool_calls": [],
                "citations": [],
                "session_id": "ui-sess-1",
                "approval_required": True,
                "approval_status": "pending",
                "pending_tool": {
                    "tool": "k8s_quantity_converter",
                    "arguments": {"quantity": "1Gi", "compare_to": "1G"},
                },
                "execution_trace": [],
            },
        )
        data = run_agent("Compare 1Gi and 1G", session_id="ui-sess-1", base_url="http://127.0.0.1:8000")
        self.assertTrue(data["approval_required"])
        self.assertEqual(data["session_id"], "ui-sess-1")
        self.assertEqual(data["pending_tool"]["tool"], "k8s_quantity_converter")

    @patch("ui.api_client.requests.request")
    def test_05_api_connection_failure_and_timeout(self, mock_req: MagicMock) -> None:
        """Handles connection refusal and request timeouts without crashing."""
        mock_req.side_effect = requests.exceptions.ConnectionError("refused")
        with self.assertRaises(BackendAPIError) as ctx_conn:
            ask_rag("What is a Pod?")
        self.assertIn("Unable to reach KubeCoach backend", ctx_conn.exception.message)

        mock_req.side_effect = requests.exceptions.Timeout("timed out")
        with self.assertRaises(BackendAPIError) as ctx_time:
            ask_rag("What is a Pod?", timeout=5.0)
        self.assertIn("timed out", ctx_time.exception.message.lower())

    @patch("ui.api_client.requests.request")
    def test_06_invalid_backend_response(self, mock_req: MagicMock) -> None:
        """Rejects non-JSON bodies and payloads missing required contract fields."""
        mock_req.return_value = _mock_response(502, bad_json=True)
        with self.assertRaises(BackendAPIError) as ctx_bad:
            ask_rag("What is a Pod?")
        self.assertIn("invalid non-JSON", ctx_bad.exception.message)

        mock_req.return_value = _mock_response(200, {"unexpected": "payload"})
        with self.assertRaises(BackendAPIError) as ctx_missing:
            ask_rag("What is a Pod?")
        self.assertIn("missing 'answer'", ctx_missing.exception.message)

    @patch("ui.api_client.requests.request")
    def test_07_approval_and_rejection_flow(self, mock_req: MagicMock) -> None:
        """Supports approving and rejecting pending LangGraph tool execution via /agent/approve."""
        # Approval accepted
        mock_req.return_value = _mock_response(
            200,
            {
                "question": "Convert 500m CPU to cores",
                "answer": "500m CPU equals 0.5 cores (500m).",
                "tool_calls": [{"tool": "k8s_quantity_converter", "success": True}],
                "citations": [],
                "session_id": "ui-hitl-1",
                "approval_required": False,
                "approval_status": "approved",
            },
        )
        approved_res = approve_agent("ui-hitl-1", approved=True)
        self.assertEqual(approved_res["approval_status"], "approved")
        self.assertIn("0.5 cores", approved_res["answer"])

        # Approval rejected
        mock_req.return_value = _mock_response(
            200,
            {
                "question": "Convert 500m CPU to cores",
                "answer": "Execution was rejected by the user. The tool was not executed.",
                "tool_calls": [],
                "citations": [],
                "session_id": "ui-hitl-2",
                "approval_required": False,
                "approval_status": "rejected",
            },
        )
        rejected_res = approve_agent("ui-hitl-2", approved=False)
        self.assertEqual(rejected_res["approval_status"], "rejected")
        self.assertEqual(rejected_res["tool_calls"], [])


class TestDay10CitationsAndRelationships(unittest.TestCase):
    """Tests for citation formatting and Signature Kubernetes Object Relationship Strip."""

    def test_08_citation_rendering_with_sources_and_empty_notice(self) -> None:
        """Renders clickable official URLs + page metadata, or clear missing-source notice."""
        citations = [
            {
                "document_title": "Deployments",
                "source_url": "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
                "page": "deployment.md",
            }
        ]
        html_out = format_citations_html(citations, context_sufficient=True)
        self.assertIn("Deployments", html_out)
        self.assertIn("https://kubernetes.io/docs/concepts/workloads/controllers/deployment/", html_out)
        self.assertIn("deployment.md", html_out)
        self.assertIn('target="_blank"', html_out)

        # Insufficient context notice (e.g., Q6 Istio)
        empty_html = format_citations_html([], context_sufficient=False)
        self.assertIn("No verified official Kubernetes documentation source", empty_html)

        # Pure quantity converter in Agent Mode omits empty citation warning
        conv_html = format_citations_html(
            [],
            context_sufficient=True,
            mode="agent",
            tool_calls=[{"tool": "k8s_quantity_converter"}],
        )
        self.assertEqual(conv_html, "")

    def test_09_object_relationship_mapping_verified_chains(self) -> None:
        """Verifies accurate Kubernetes object relationship strips for all key object groups."""
        # Deployment + Service -> signature strip Deployment → ReplicaSet → Pods ← Service
        strip_ds = extract_object_relationships(
            question="How does a Service expose a Deployment?",
            answer="A Deployment manages a ReplicaSet of Pods, and a Service routes traffic to those Pods.",
        )
        self.assertIsNotNone(strip_ds)
        self.assertEqual(strip_ds["plain_text"], "Deployment → ReplicaSet → Pods ← Service")
        self.assertIn("Deployment", strip_ds["highlighted_labels"])
        self.assertIn("Service", strip_ds["highlighted_labels"])

        # Deployment + Pod -> Deployment → ReplicaSet → Pods
        strip_dep = extract_object_relationships(
            question="What is the difference between a Pod and a Deployment?",
            answer="A Deployment declaratively manages ReplicaSets and Pods.",
        )
        self.assertEqual(strip_dep["plain_text"], "Deployment → ReplicaSet → Pods")

        # ConfigMap + Secret -> ConfigMap → Pod ← Secret
        strip_cfg = extract_object_relationships(
            question="What is the difference between ConfigMap and Secret?",
            answer="ConfigMap stores non-sensitive config and Secret stores credentials mounted into a Pod.",
        )
        self.assertEqual(strip_cfg["plain_text"], "ConfigMap → Pod ← Secret")

        # StatefulSet -> StatefulSet → Pods
        strip_sts = extract_object_relationships(
            question="When do I use a StatefulSet?",
            answer="A StatefulSet manages stateful Pods with stable network identities.",
        )
        self.assertEqual(strip_sts["plain_text"], "StatefulSet → Pods")

        # DaemonSet -> DaemonSet → Pods
        strip_ds_ctrl = extract_object_relationships(
            question="How to run a pod on every node?",
            answer="Use a DaemonSet to run a Pod copy on every node.",
        )
        self.assertEqual(strip_ds_ctrl["plain_text"], "DaemonSet → Pods")

        # PVC -> PV
        strip_pvc = extract_object_relationships(
            question="Difference between PersistentVolume and PersistentVolumeClaim?",
            answer="A PersistentVolumeClaim binds to an available PersistentVolume.",
        )
        self.assertEqual(strip_pvc["plain_text"], "PersistentVolumeClaim → PersistentVolume")

    def test_10_object_relationship_omitted_on_refusal_and_unrelated(self) -> None:
        """Never displays unrelated or fabricated object strips on Q6 refusal or non-K8s text."""
        q6_strip = extract_object_relationships(
            question="How do I configure an Istio Service Mesh with Mutual TLS?",
            answer="I don't know based on the provided official Kubernetes documentation.",
            context_sufficient=False,
        )
        self.assertIsNone(q6_strip)

        # Ensure "service mesh" alone does not falsely trigger Kubernetes Service
        mentioned = detect_mentioned_objects(
            question="Istio service mesh overview",
            answer="External service mesh topic.",
        )
        self.assertNotIn("Service", mentioned)

        # HTML rendering includes tooltips and highlights
        strip_svc = extract_object_relationships(
            question="Explain Kubernetes Services",
            answer="A Service exposes a logical set of Pods with a stable IP.",
        )
        rendered = render_relationship_strip_html(strip_svc)
        self.assertIn("kc-rel-node-active", rendered)
        self.assertIn("→", rendered)
        self.assertIn("title=", rendered)


class TestDay10FeedbackPersistenceAndSession(unittest.TestCase):
    """Tests for POST /feedback persistence, duplicate prevention, and session history."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_feedback_path = main_module.FEEDBACK_FILE_PATH
        main_module.FEEDBACK_FILE_PATH = Path(self._tmpdir.name) / "feedback.json"
        self.client = TestClient(main_module.app)

    def tearDown(self) -> None:
        main_module.FEEDBACK_FILE_PATH = self._orig_feedback_path
        self._tmpdir.cleanup()

    def test_11_feedback_submission_persistence_and_duplicate_block(self) -> None:
        """POST /feedback persists to JSON, prevents duplicates (409), and validates input (422)."""
        r1 = self.client.post(
            "/feedback",
            json={
                "response_id": "resp-001",
                "session_id": "ui-sess-abc",
                "question": "What is a Pod?",
                "feedback": "up",
                "mode": "rag",
            },
        )
        self.assertEqual(r1.status_code, 201)
        data = r1.json()
        self.assertEqual(data["status"], "saved")
        self.assertEqual(data["feedback"], "up")
        self.assertTrue(main_module.FEEDBACK_FILE_PATH.exists())

        saved_list = json.loads(main_module.FEEDBACK_FILE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(saved_list), 1)
        self.assertEqual(saved_list[0]["response_id"], "resp-001")
        self.assertIn("timestamp", saved_list[0])

        # Duplicate submission for same (session_id, response_id) returns 409 Conflict
        dup = self.client.post(
            "/feedback",
            json={
                "response_id": "resp-001",
                "session_id": "ui-sess-abc",
                "feedback": "down",
                "mode": "rag",
            },
        )
        self.assertEqual(dup.status_code, 409)

        # Invalid feedback type returns 422
        bad = self.client.post(
            "/feedback",
            json={
                "response_id": "resp-002",
                "session_id": "ui-sess-abc",
                "feedback": "maybe",
                "mode": "rag",
            },
        )
        self.assertEqual(bad.status_code, 422)

        # GET /feedback summary matches stored records
        listing = self.client.get("/feedback")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["total"], 1)
        self.assertEqual(listing.json()["helpful"], 1)

    @patch("ui.api_client.requests.request")
    def test_12_feedback_client_helper(self, mock_req: MagicMock) -> None:
        """Client `submit_feedback` posts structured payload to /feedback."""
        mock_req.return_value = _mock_response(
            201,
            {
                "status": "saved",
                "feedback_id": "fb-12345678",
                "response_id": "resp-99",
                "session_id": "ui-1",
                "feedback": "down",
                "mode": "agent",
                "timestamp": "2026-11-18T10:00:00Z",
            },
        )
        res = submit_feedback("resp-99", "ui-1", "down", question="Test", mode="agent")
        self.assertEqual(res["status"], "saved")
        self.assertEqual(res["feedback"], "down")

    @patch("ui.app.ask_rag")
    def test_13_session_history_and_new_chat_reset(self, mock_ask: MagicMock) -> None:
        """Preserves session history across turns and cleanly resets on New Chat."""
        mock_ask.return_value = {
            "question": "What is a Pod?",
            "answer": "A Pod wraps one or more containers.",
            "citations": [],
            "retrieved_chunks": [],
            "confidence": "high",
            "context_sufficient": True,
        }
        state: Dict[str, Any] = {}
        initialize_session_state(state)
        first_sid = state["session_id"]

        msg = execute_user_query("What is a Pod?", mode="rag", session_id=first_sid)
        state["messages"].append({"role": "user", "content": "What is a Pod?"})
        state["messages"].append(msg)
        state["feedback_submitted"][msg["response_id"]] = "up"

        self.assertEqual(len(state["messages"]), 2)
        self.assertIsNotNone(msg["relationship_strip"])

        reset_chat_session(state)
        self.assertEqual(state["messages"], [])
        self.assertEqual(state["feedback_submitted"], {})
        self.assertNotEqual(state["session_id"], first_sid)

    @patch("ui.api_client.requests.request")
    def test_14_streamlit_app_starts_cleanly(self, mock_req: MagicMock) -> None:
        """Streamlit AppTest launches ui/app.py cleanly with zero exceptions and renders starter prompts."""
        from streamlit.testing.v1 import AppTest

        mock_req.return_value = _mock_response(
            200,
            {"status": "ok", "app": "KubeCoach API", "version": "1.0.0", "records_count": 18},
        )
        at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "ui" / "app.py"))
        at.run(timeout=15)
        self.assertFalse(at.exception, f"Streamlit app raised unexpected exception: {at.exception}")
        self.assertEqual(len(STARTER_QUESTIONS), 5)


if __name__ == "__main__":
    unittest.main()
