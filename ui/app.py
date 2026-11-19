"""
ui/app.py - KubeCoach Professional Streamlit Interface (Day 10)

Developer-tool chat UI communicating exclusively with the KubeCoach FastAPI
backend via HTTP (`ui/api_client.py`):
- RAG Mode (`POST /ask`) with verified citations and honest refusal handling
- Agent Mode (`POST /agent` & `POST /agent/approve`) with LangGraph HITL approval
- Signature Feature: Kubernetes Object Relationship Strip (`ui/relationships.py`)
- Persistent thumbs-up / thumbs-down feedback (`POST /feedback` -> `data/feedback.json`)
"""

from __future__ import annotations

import html
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Ensure repository root is importable regardless of launch directory
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui.api_client import (
    BackendAPIError,
    approve_agent,
    ask_rag,
    check_health,
    get_api_base_url,
    run_agent,
    submit_feedback,
)
from ui.relationships import (
    extract_object_relationships,
    render_relationship_strip_html,
)

# ---------------------------------------------------------------------------
# Constants & Starter Content
# ---------------------------------------------------------------------------

PRODUCT_NAME = "KubeCoach"
PRODUCT_TAGLINE = "Your Personal Kubernetes Learning Assistant"
PRODUCT_DESCRIPTION = (
    "Understand Kubernetes objects, commands and relationships in simple language."
)

STARTER_QUESTIONS: List[str] = [
    "What is the difference between a Pod and a Deployment?",
    "Explain Kubernetes Services with an example.",
    "What does kubectl get pods do?",
    "What is the difference between ConfigMap and Secret?",
    "Explain Liveness and Readiness probes.",
]

EXAMPLE_TOPICS: List[str] = [
    "Pods & Deployments",
    "Services & Ingress",
    "ConfigMaps & Secrets",
    "StatefulSets & Storage (PV/PVC)",
    "RBAC & Namespaces",
    "CPU/Memory Units (Agent Mode)",
]

# ---------------------------------------------------------------------------
# Minimal, Developer-Tool Custom CSS (Dark Navy/Charcoal + Subtle Blue)
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
    /* Global layout refinement */
    .stApp {
        background-color: #0B1120;
        color: #F1F5F9;
    }

    section[data-testid="stSidebar"] {
        background-color: #111827;
        border-right: 1px solid #1E293B;
    }

    /* Main container width & spacing */
    .block-container {
        max-width: 920px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    /* Top header block */
    .kc-header {
        border-bottom: 1px solid #1E293B;
        padding-bottom: 1rem;
        margin-bottom: 1.5rem;
    }
    .kc-title-row {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        flex-wrap: wrap;
    }
    .kc-title {
        font-size: 1.65rem;
        font-weight: 700;
        color: #F8FAFC;
        letter-spacing: -0.02em;
        margin: 0;
    }
    .kc-badge {
        font-size: 0.72rem;
        font-weight: 600;
        color: #60A5FA;
        background-color: #172554;
        border: 1px solid #1E3A8A;
        border-radius: 999px;
        padding: 0.15rem 0.6rem;
        letter-spacing: 0.03em;
    }
    .kc-tagline {
        font-size: 0.98rem;
        font-weight: 500;
        color: #CBD5E1;
        margin: 0.25rem 0 0.15rem 0;
    }
    .kc-desc {
        font-size: 0.86rem;
        color: #94A3B8;
        margin: 0;
    }

    /* Sidebar status pill */
    .kc-status {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.55rem 0.75rem;
        border-radius: 8px;
        font-size: 0.82rem;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }
    .kc-status-ok {
        background-color: #0F291E;
        border: 1px solid #14532D;
        color: #86EFAC;
    }
    .kc-status-err {
        background-color: #2A1215;
        border: 1px solid #7F1D1D;
        color: #FCA5A5;
    }
    .kc-status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        display: inline-block;
        flex-shrink: 0;
    }
    .kc-dot-ok { background-color: #22C55E; }
    .kc-dot-err { background-color: #EF4444; }

    /* Signature Feature: Kubernetes Object Relationship Strip */
    .kc-rel-container {
        background-color: #0F172A;
        border: 1px solid #1E293B;
        border-left: 3px solid #3B82F6;
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin-top: 0.85rem;
        margin-bottom: 0.75rem;
    }
    .kc-rel-header {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        color: #60A5FA;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }
    .kc-rel-strip {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.45rem;
        margin-bottom: 0.55rem;
    }
    .kc-rel-node {
        display: inline-flex;
        align-items: center;
        padding: 0.3rem 0.7rem;
        border-radius: 6px;
        font-size: 0.82rem;
        font-weight: 500;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        background-color: #111827;
        border: 1px solid #334155;
        color: #94A3B8;
        cursor: help;
    }
    .kc-rel-node-active {
        background-color: #172554;
        border: 1px solid #3B82F6;
        color: #EFF6FF;
        font-weight: 600;
    }
    .kc-rel-arrow {
        color: #60A5FA;
        font-size: 0.95rem;
        font-weight: 700;
        padding: 0 0.1rem;
        user-select: none;
    }
    .kc-rel-legend {
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        border-top: 1px solid #1E293B;
        padding-top: 0.5rem;
        font-size: 0.76rem;
        color: #94A3B8;
    }
    .kc-rel-legend-item strong {
        color: #CBD5E1;
    }

    /* Citations container (visually distinct from main answer) */
    .kc-citations {
        background-color: #111827;
        border: 1px solid #1E293B;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        margin-top: 0.65rem;
        margin-bottom: 0.65rem;
    }
    .kc-citations-title {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        color: #94A3B8;
        text-transform: uppercase;
        margin-bottom: 0.45rem;
    }
    .kc-citation-item {
        font-size: 0.82rem;
        color: #CBD5E1;
        margin-bottom: 0.3rem;
        line-height: 1.4;
    }
    .kc-citation-item a {
        color: #60A5FA;
        text-decoration: none;
    }
    .kc-citation-item a:hover {
        text-decoration: underline;
    }
    .kc-citation-meta {
        color: #64748B;
        font-size: 0.76rem;
        margin-left: 0.35rem;
    }
    .kc-no-citation {
        font-size: 0.82rem;
        color: #94A3B8;
        font-style: italic;
    }

    /* Human Approval Card (Agent Mode) */
    .kc-approval-box {
        background-color: #1E1B2E;
        border: 1px solid #4C1D95;
        border-left: 3px solid #3B82F6;
        border-radius: 8px;
        padding: 0.85rem 1rem;
        margin-top: 0.75rem;
        margin-bottom: 0.6rem;
    }
    .kc-approval-title {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        color: #93C5FD;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }

    /* Feedback confirmation pill */
    .kc-feedback-confirm {
        font-size: 0.78rem;
        color: #86EFAC;
        margin-top: 0.25rem;
    }

    /* Starter section label */
    .kc-section-label {
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.05em;
        color: #94A3B8;
        text-transform: uppercase;
        margin-bottom: 0.6rem;
    }

    /* Subtle styling for topic chips in sidebar */
    .kc-topic-list {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin-top: 0.25rem;
    }
    .kc-topic-chip {
        font-size: 0.74rem;
        color: #CBD5E1;
        background-color: #0F172A;
        border: 1px solid #1E293B;
        border-radius: 6px;
        padding: 0.2rem 0.5rem;
    }

    /* Mobile responsiveness */
    @media (max-width: 640px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
        .kc-rel-node {
            font-size: 0.76rem;
            padding: 0.25rem 0.55rem;
        }
    }
</style>
"""


# ---------------------------------------------------------------------------
# Pure Rendering Helpers (Unit-Testable Without Streamlit Runtime)
# ---------------------------------------------------------------------------

def format_citations_html(
    citations: Optional[List[Dict[str, Any]]],
    context_sufficient: bool = True,
    mode: str = "rag",
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Format backend citations into a visually separated HTML panel.

    Never fabricates citations; shows a clear notice when no verified source is available.
    """
    valid_citations = [
        c for c in (citations or [])
        if isinstance(c, dict) and (c.get("document_title") or c.get("source_url"))
    ]

    # For pure quantity converter agent runs (no RAG search called), skip empty citation warning
    if mode == "agent" and not valid_citations and tool_calls:
        used_tools = {tc.get("tool") for tc in tool_calls if isinstance(tc, dict)}
        if used_tools == {"k8s_quantity_converter"}:
            return ""

    if not valid_citations:
        if not context_sufficient:
            msg = "No verified official Kubernetes documentation source covers this topic."
        else:
            msg = "No reliable documentation source available for this response."
        return (
            '<div class="kc-citations">'
            '  <div class="kc-citations-title">Sources</div>'
            f'  <div class="kc-no-citation">{html.escape(msg)}</div>'
            "</div>"
        )

    items_html: List[str] = []
    for idx, cite in enumerate(valid_citations, start=1):
        title = html.escape(str(cite.get("document_title") or "Official Kubernetes Documentation"))
        url = str(cite.get("source_url") or "").strip()
        page = str(cite.get("page") or cite.get("section") or "").strip()
        page_badge = f'<span class="kc-citation-meta">({html.escape(page)})</span>' if page else ""

        if url.startswith(("http://", "https://")):
            safe_url = html.escape(url, quote=True)
            link_markup = f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">{title}</a>'
        else:
            link_markup = f"<span>{title}</span>"

        items_html.append(f'<div class="kc-citation-item">[{idx}] {link_markup}{page_badge}</div>')

    return (
        '<div class="kc-citations">'
        '  <div class="kc-citations-title">Verified Documentation Sources</div>'
        f'  {"".join(items_html)}'
        "</div>"
    )


def create_new_session_id() -> str:
    """Generate a unique session identifier for Streamlit and LangGraph memory."""
    return f"ui-{uuid.uuid4().hex[:8]}"


def initialize_session_state(state: Optional[Dict[str, Any]] = None) -> None:
    """Initialize required Streamlit session state keys safely."""
    target = state if state is not None else st.session_state
    if "session_id" not in target:
        target["session_id"] = create_new_session_id()
    if "messages" not in target:
        target["messages"] = []
    if "chat_mode" not in target:
        target["chat_mode"] = "rag"
    if "feedback_submitted" not in target:
        target["feedback_submitted"] = {}
    if "queued_prompt" not in target:
        target["queued_prompt"] = None


def reset_chat_session(state: Optional[Dict[str, Any]] = None) -> None:
    """Reset chat history, feedback map, and start a fresh isolated session ID."""
    target = state if state is not None else st.session_state
    target["session_id"] = create_new_session_id()
    target["messages"] = []
    target["feedback_submitted"] = {}
    target["queued_prompt"] = None


# ---------------------------------------------------------------------------
# Backend Query & Approval Handlers
# ---------------------------------------------------------------------------

def execute_user_query(question: str, mode: str, session_id: str) -> Dict[str, Any]:
    """Send user prompt to the appropriate FastAPI endpoint and build a structured chat message."""
    response_id = f"resp-{uuid.uuid4().hex[:8]}"

    if mode == "agent":
        data = run_agent(question=question, session_id=session_id)
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        tool_calls = data.get("tool_calls", [])
        approval_required = bool(data.get("approval_required", False))
        approval_status = str(data.get("approval_status", "not_required"))
        pending_tool = data.get("pending_tool")
        execution_trace = data.get("execution_trace", [])
        context_sufficient = "i don't know" not in answer.lower()

        relationship_strip = None
        if not approval_required and approval_status != "rejected":
            relationship_strip = extract_object_relationships(
                question=question,
                answer=answer,
                citations=citations,
                context_sufficient=context_sufficient,
            )

        return {
            "role": "assistant",
            "response_id": response_id,
            "question": question,
            "content": answer,
            "mode": "agent",
            "citations": citations,
            "context_sufficient": context_sufficient,
            "relationship_strip": relationship_strip,
            "tool_calls": tool_calls,
            "approval_required": approval_required,
            "approval_status": approval_status,
            "pending_tool": pending_tool,
            "execution_trace": execution_trace,
            "session_id": data.get("session_id", session_id),
        }

    # Default: RAG Mode -> POST /ask
    data = ask_rag(question=question, top_k=3)
    answer = data.get("answer", "")
    citations = data.get("citations", [])
    retrieved_chunks = data.get("retrieved_chunks", [])
    context_sufficient = bool(data.get("context_sufficient", True))
    confidence = data.get("confidence", "medium")

    relationship_strip = extract_object_relationships(
        question=question,
        answer=answer,
        citations=citations,
        retrieved_chunks=retrieved_chunks,
        context_sufficient=context_sufficient,
    )

    return {
        "role": "assistant",
        "response_id": response_id,
        "question": question,
        "content": answer,
        "mode": "rag",
        "citations": citations,
        "retrieved_chunks": retrieved_chunks,
        "context_sufficient": context_sufficient,
        "confidence": confidence,
        "relationship_strip": relationship_strip,
        "approval_required": False,
        "approval_status": "not_required",
        "session_id": session_id,
    }


def handle_approval_decision(message_index: int, approved: bool) -> None:
    """Submit human approval or rejection for a paused Agent Mode message."""
    msg = st.session_state.messages[message_index]
    sid = msg.get("session_id") or st.session_state.session_id

    try:
        with st.spinner("Resuming LangGraph workflow..."):
            resumed = approve_agent(session_id=sid, approved=approved)

        answer = resumed.get("answer", "")
        citations = resumed.get("citations", [])
        approval_status = str(resumed.get("approval_status", "approved" if approved else "rejected"))
        tool_calls = resumed.get("tool_calls", [])
        execution_trace = resumed.get("execution_trace", [])

        relationship_strip = None
        if approved:
            relationship_strip = extract_object_relationships(
                question=msg.get("question", ""),
                answer=answer,
                citations=citations,
                context_sufficient=True,
            )

        st.session_state.messages[message_index].update({
            "content": answer,
            "citations": citations,
            "tool_calls": tool_calls,
            "approval_required": False,
            "approval_status": approval_status,
            "pending_tool": None,
            "execution_trace": execution_trace,
            "relationship_strip": relationship_strip,
        })
    except BackendAPIError as exc:
        st.error(f"Could not process approval decision: {exc.message}")


# ---------------------------------------------------------------------------
# Sidebar Renderer
# ---------------------------------------------------------------------------

def render_sidebar(health_info: Dict[str, Any]) -> None:
    """Render KubeCoach branding, navigation, mode toggle, backend status, and metadata."""
    with st.sidebar:
        st.markdown(f"### {PRODUCT_NAME}")
        st.caption(PRODUCT_TAGLINE)

        if st.button("New Chat", use_container_width=True, type="primary"):
            reset_chat_session()
            st.rerun()

        st.divider()

        # Chat Mode Toggle
        st.markdown('<div class="kc-section-label">Chat Mode</div>', unsafe_allow_html=True)
        mode_labels = {
            "rag": "RAG Mode (/ask)",
            "agent": "Agent Mode (/agent)",
        }
        selected_mode = st.radio(
            label="Select Assistant Mode",
            options=["rag", "agent"],
            format_func=lambda k: mode_labels[k],
            index=0 if st.session_state.chat_mode == "rag" else 1,
            label_visibility="collapsed",
        )
        st.session_state.chat_mode = selected_mode

        if selected_mode == "rag":
            st.caption("Grounded answers strictly from official Kubernetes docs with citations.")
        else:
            st.caption(
                "LangGraph agent with tool selection, MemorySaver, and human approval for CPU/Memory unit conversions."
            )

        st.divider()

        # Live Backend Health Status
        st.markdown('<div class="kc-section-label">Backend Status</div>', unsafe_allow_html=True)
        if health_info.get("connected"):
            rec_count = health_info.get("records_count", 0)
            st.markdown(
                '<div class="kc-status kc-status-ok">'
                '  <span class="kc-status-dot kc-dot-ok"></span>'
                f'  <span>Connected &middot; {rec_count} records</span>'
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="kc-status kc-status-err">'
                '  <span class="kc-status-dot kc-dot-err"></span>'
                "  <span>Backend Disconnected</span>"
                "</div>",
                unsafe_allow_html=True,
            )
            st.caption(health_info.get("error") or "FastAPI health check failed.")

        st.caption(f"API: `{health_info.get('base_url', get_api_base_url())}`")

        st.divider()

        # Supported Features
        st.markdown('<div class="kc-section-label">Capabilities</div>', unsafe_allow_html=True)
        st.markdown(
            "- Official Kubernetes docs RAG\n"
            "- Verifiable source citations\n"
            "- Object relationship strip\n"
            "- LangGraph agent & unit converter\n"
            "- Persistent answer feedback"
        )

        # Example Kubernetes Topics
        st.markdown('<div class="kc-section-label">Example Topics</div>', unsafe_allow_html=True)
        chips = "".join(f'<span class="kc-topic-chip">{html.escape(t)}</span>' for t in EXAMPLE_TOPICS)
        st.markdown(f'<div class="kc-topic-list">{chips}</div>', unsafe_allow_html=True)

        st.divider()

        # Project Info
        st.markdown('<div class="kc-section-label">Project Info</div>', unsafe_allow_html=True)
        st.caption(
            f"**{PRODUCT_NAME}** (SJ-58)\n\n"
            "Student: Bhushan Kailas Chaturbhuj\n\n"
            f"Session: `{st.session_state.session_id}`"
        )


# ---------------------------------------------------------------------------
# Message & Feedback Renderers
# ---------------------------------------------------------------------------

def render_assistant_message(msg: Dict[str, Any], index: int) -> None:
    """Render assistant markdown response, approval gate, relationship strip, citations, and feedback."""
    st.markdown(msg.get("content", ""))

    # 1. Human-in-the-loop Approval Gate (Agent Mode)
    if msg.get("approval_required") and msg.get("pending_tool"):
        pending = msg["pending_tool"]
        tool_name = html.escape(str(pending.get("tool", "k8s_quantity_converter")))
        args_pretty = json.dumps(pending.get("arguments", {}), indent=2)

        st.markdown(
            '<div class="kc-approval-box">'
            '  <div class="kc-approval-title">Human Approval Required</div>'
            f'  <div>Proposed tool: <code>{tool_name}</code></div>'
            "</div>",
            unsafe_allow_html=True,
        )
        st.code(args_pretty, language="json")

        col_approve, col_reject, _ = st.columns([1, 1, 2])
        with col_approve:
            if st.button("Approve & Execute", key=f"approve_{msg['response_id']}", type="primary"):
                handle_approval_decision(index, approved=True)
                st.rerun()
        with col_reject:
            if st.button("Reject", key=f"reject_{msg['response_id']}"):
                handle_approval_decision(index, approved=False)
                st.rerun()
        return

    # 2. Signature Feature: Kubernetes Object Relationship Strip
    strip_data = msg.get("relationship_strip")
    if strip_data:
        strip_html = render_relationship_strip_html(strip_data)
        if strip_html:
            st.markdown(strip_html, unsafe_allow_html=True)

    # 3. Citations Panel (Visually separate from main answer)
    citations_html = format_citations_html(
        citations=msg.get("citations"),
        context_sufficient=bool(msg.get("context_sufficient", True)),
        mode=msg.get("mode", "rag"),
        tool_calls=msg.get("tool_calls"),
    )
    if citations_html:
        st.markdown(citations_html, unsafe_allow_html=True)

    # 4. Agent Mode Tool Execution Details (Collapsible)
    if msg.get("mode") == "agent" and (msg.get("tool_calls") or msg.get("execution_trace")):
        with st.expander("Agent Tool Execution & Trace", expanded=False):
            if msg.get("tool_calls"):
                st.markdown("**Executed Tool Calls**")
                st.json(msg["tool_calls"])
            if msg.get("execution_trace"):
                st.markdown("**LangGraph Execution Trace**")
                st.json(msg["execution_trace"])

    # 5. Persistent Thumbs-Up / Thumbs-Down Feedback Controls
    response_id = msg.get("response_id", f"resp-{index}")
    existing_rating = st.session_state.feedback_submitted.get(response_id)

    if existing_rating:
        label = "Helpful" if existing_rating == "up" else "Not helpful"
        st.markdown(
            f'<div class="kc-feedback-confirm">Feedback saved: {label}</div>',
            unsafe_allow_html=True,
        )
    else:
        col_up, col_down, _ = st.columns([1.2, 1.5, 5])
        with col_up:
            if st.button("👍 Helpful", key=f"fb_up_{response_id}", use_container_width=True):
                _submit_ui_feedback(msg, rating="up")
                st.rerun()
        with col_down:
            if st.button("👎 Not helpful", key=f"fb_down_{response_id}", use_container_width=True):
                _submit_ui_feedback(msg, rating="down")
                st.rerun()


def _submit_ui_feedback(msg: Dict[str, Any], rating: str) -> None:
    """Persist feedback through FastAPI POST /feedback and update session state."""
    response_id = msg.get("response_id", "")
    session_id = msg.get("session_id") or st.session_state.session_id
    try:
        submit_feedback(
            response_id=response_id,
            session_id=session_id,
            feedback=rating,
            question=msg.get("question", ""),
            mode=msg.get("mode", "rag"),
        )
        st.session_state.feedback_submitted[response_id] = rating
    except BackendAPIError as exc:
        if exc.status_code == 409:
            st.session_state.feedback_submitted[response_id] = rating
        else:
            st.error(f"Could not save feedback: {exc.message}")


# ---------------------------------------------------------------------------
# Main Application Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    """Render the KubeCoach Streamlit developer-tool chat application."""
    st.set_page_config(
        page_title=f"{PRODUCT_NAME} — {PRODUCT_TAGLINE}",
        page_icon="⎈",
        layout="centered",
        initial_sidebar_state="expanded",
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    initialize_session_state()
    health_info = check_health()
    render_sidebar(health_info)

    # Header
    mode_badge = "RAG MODE" if st.session_state.chat_mode == "rag" else "AGENT MODE"
    st.markdown(
        '<div class="kc-header">'
        '  <div class="kc-title-row">'
        f'    <h1 class="kc-title">{PRODUCT_NAME}</h1>'
        f'    <span class="kc-badge">{mode_badge}</span>'
        "  </div>"
        f'  <p class="kc-tagline">{PRODUCT_TAGLINE}</p>'
        f'  <p class="kc-desc">{PRODUCT_DESCRIPTION}</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    if not health_info.get("connected"):
        st.warning(
            f"FastAPI backend is not reachable at `{health_info.get('base_url')}`. "
            "Start the backend with `uvicorn app.main:app --port 8000` before asking questions."
        )

    # Empty state: Suggested Starter Questions
    if not st.session_state.messages:
        st.markdown('<div class="kc-section-label">Suggested Questions</div>', unsafe_allow_html=True)
        for idx, starter in enumerate(STARTER_QUESTIONS):
            if st.button(starter, key=f"starter_{idx}", use_container_width=True):
                st.session_state.queued_prompt = starter
                st.rerun()

    # Render Conversation History
    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.markdown(msg.get("content", ""))
            else:
                render_assistant_message(msg, index=idx)

    # Chat Input at Bottom
    placeholder = (
        "Ask a Kubernetes question (e.g., What is a Deployment?)..."
        if st.session_state.chat_mode == "rag"
        else "Ask Kubernetes docs or convert units (e.g., Compare 1Gi and 1G memory)..."
    )
    user_input = st.chat_input(placeholder)

    prompt_to_run = user_input or st.session_state.queued_prompt
    if prompt_to_run:
        st.session_state.queued_prompt = None
        cleaned_prompt = prompt_to_run.strip()
        if cleaned_prompt:
            st.session_state.messages.append({"role": "user", "content": cleaned_prompt})
            with st.chat_message("user"):
                st.markdown(cleaned_prompt)

            with st.chat_message("assistant"):
                spinner_text = (
                    "Retrieving official Kubernetes documentation..."
                    if st.session_state.chat_mode == "rag"
                    else "Running LangGraph agent workflow..."
                )
                try:
                    with st.spinner(spinner_text):
                        assistant_msg = execute_user_query(
                            question=cleaned_prompt,
                            mode=st.session_state.chat_mode,
                            session_id=st.session_state.session_id,
                        )
                    st.session_state.messages.append(assistant_msg)
                    st.rerun()
                except BackendAPIError as exc:
                    error_msg = {
                        "role": "assistant",
                        "response_id": f"err-{uuid.uuid4().hex[:8]}",
                        "question": cleaned_prompt,
                        "content": f"**Backend Request Error:** {exc.message}",
                        "mode": st.session_state.chat_mode,
                        "citations": [],
                        "context_sufficient": False,
                        "relationship_strip": None,
                        "approval_required": False,
                        "approval_status": "not_required",
                        "session_id": st.session_state.session_id,
                    }
                    st.error(exc.message)
                    st.session_state.messages.append(error_msg)


if __name__ == "__main__":
    main()
