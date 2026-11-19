"""
ui/api_client.py - HTTP Client for KubeCoach FastAPI Backend (Day 10)

All Streamlit communication flows exclusively through this HTTP client.
No LLM, RAG, vector store, or agent logic is duplicated in the frontend.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

logger = logging.getLogger("kubecoach.ui.api_client")

# Load local .env if present (safe no-op if absent)
_REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_REPO_ROOT / ".env")

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_HEALTH_TIMEOUT = 4.0
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_FEEDBACK_TIMEOUT = 10.0


class BackendAPIError(Exception):
    """Structured exception raised when FastAPI communication fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_api_base_url() -> str:
    """Return normalized FastAPI base URL from API_BASE_URL env var or local default."""
    raw = os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).strip()
    if not raw:
        return DEFAULT_API_BASE_URL
    return raw.rstrip("/")


def _parse_json_response(response: requests.Response, endpoint: str) -> Dict[str, Any]:
    """Parse and validate a JSON dictionary response from the FastAPI backend."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise BackendAPIError(
            f"Backend returned an invalid non-JSON response from {endpoint} (HTTP {response.status_code}).",
            status_code=response.status_code,
        ) from exc

    if not isinstance(payload, dict):
        raise BackendAPIError(
            f"Unexpected response format from {endpoint}: expected JSON object.",
            status_code=response.status_code,
        )

    if response.status_code >= 400:
        detail = payload.get("detail") or payload.get("error") or response.reason or "Request failed"
        raise BackendAPIError(
            f"Backend error (HTTP {response.status_code}): {detail}",
            status_code=response.status_code,
        )

    return payload


def _request_json(
    method: str,
    endpoint: str,
    json_body: Optional[Dict[str, Any]] = None,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Execute an HTTP request against the FastAPI backend with consistent error handling."""
    root = (base_url or get_api_base_url()).rstrip("/")
    url = f"{root}{endpoint}"

    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            json=json_body,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
    except requests.exceptions.Timeout as exc:
        logger.warning("Request timed out for %s %s", method, url)
        raise BackendAPIError(
            f"Request to {endpoint} timed out after {timeout:.0f}s. "
            "Check that the FastAPI server is healthy and not overloaded."
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        logger.warning("Connection failed for %s %s", method, url)
        raise BackendAPIError(
            f"Unable to reach KubeCoach backend at {root}. "
            "Ensure FastAPI is running (uvicorn app.main:app --port 8000)."
        ) from exc
    except requests.exceptions.RequestException as exc:
        logger.error("HTTP transport error for %s %s: %s", method, url, exc)
        raise BackendAPIError(f"Network error contacting backend: {exc}") from exc

    return _parse_json_response(response, endpoint=endpoint)


def check_health(
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_HEALTH_TIMEOUT,
) -> Dict[str, Any]:
    """Verify FastAPI reachability via GET /health.

    Never reports connected unless HTTP 200 with status=='ok' is received.
    """
    root = (base_url or get_api_base_url()).rstrip("/")
    try:
        data = _request_json("GET", "/health", base_url=root, timeout=timeout)
        if data.get("status") != "ok":
            return {
                "connected": False,
                "base_url": root,
                "error": f"Unexpected health status: {data.get('status')}",
                "data": data,
            }
        return {
            "connected": True,
            "base_url": root,
            "records_count": data.get("records_count", 0),
            "version": data.get("version", "unknown"),
            "app": data.get("app", "KubeCoach API"),
            "error": None,
        }
    except BackendAPIError as exc:
        return {
            "connected": False,
            "base_url": root,
            "records_count": 0,
            "error": exc.message,
        }


def ask_rag(
    question: str,
    top_k: int = 3,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Call POST /ask for grounded RAG documentation answering with citations."""
    data = _request_json(
        "POST",
        "/ask",
        json_body={"question": question.strip(), "top_k": top_k},
        base_url=base_url,
        timeout=timeout,
    )
    if "answer" not in data:
        raise BackendAPIError("Invalid /ask response: missing 'answer' field.")
    return data


def run_agent(
    question: str,
    session_id: Optional[str] = None,
    approved: Optional[bool] = None,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Call POST /agent to execute or resume the stateful LangGraph agent."""
    body: Dict[str, Any] = {"question": question.strip()}
    if session_id:
        body["session_id"] = session_id
    if approved is not None:
        body["approved"] = approved

    data = _request_json(
        "POST",
        "/agent",
        json_body=body,
        base_url=base_url,
        timeout=timeout,
    )
    if "answer" not in data or "session_id" not in data:
        raise BackendAPIError("Invalid /agent response: missing required 'answer' or 'session_id'.")
    return data


def approve_agent(
    session_id: str,
    approved: bool,
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_REQUEST_TIMEOUT,
) -> Dict[str, Any]:
    """Call POST /agent/approve to approve or reject a paused LangGraph interrupt."""
    data = _request_json(
        "POST",
        "/agent/approve",
        json_body={"session_id": session_id.strip(), "approved": bool(approved)},
        base_url=base_url,
        timeout=timeout,
    )
    if "answer" not in data:
        raise BackendAPIError("Invalid /agent/approve response: missing 'answer' field.")
    return data


def submit_feedback(
    response_id: str,
    session_id: str,
    feedback: str,
    question: str = "",
    mode: str = "rag",
    base_url: Optional[str] = None,
    timeout: float = DEFAULT_FEEDBACK_TIMEOUT,
) -> Dict[str, Any]:
    """Persist thumbs-up / thumbs-down feedback via POST /feedback."""
    return _request_json(
        "POST",
        "/feedback",
        json_body={
            "response_id": response_id,
            "session_id": session_id,
            "feedback": feedback,
            "question": question,
            "mode": mode,
        },
        base_url=base_url,
        timeout=timeout,
    )
