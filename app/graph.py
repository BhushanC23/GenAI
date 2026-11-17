"""
app/graph.py - LangGraph Stateful Workflow for KubeCoach (Day 9)

Implements a stateful AI agent graph:
- AgentState: TypedDict defining graph memory and execution context
- Nodes:
    1. reasoner: LLM/Heuristic planner deciding next action or direct answer
    2. approval_gate: Human-in-the-loop (HITL) approval gate for project-card tool (k8s_quantity_converter)
    3. tool_executor: Safe read-only dispatcher executing approved tools
    4. synthesizer: Synthesizes final answer with citations
- Edges:
    - Conditional routing from reasoner (tool_call vs final_answer)
    - Conditional routing from approval_gate (pending_approval, rejected, approved)
    - Execution edge to synthesizer
- Multi-turn Conversation Memory: In-memory Checkpointer / Session Store keyed by session_id.
"""

from __future__ import annotations
import copy
import json
import logging
import re
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from typing_extensions import TypedDict

from app.agent_loop import _detect_tool_call_intent
from app.llm import generate_chat_response
from app.tools import execute_tool

logger = logging.getLogger("kubecoach.graph")

END = "__end__"

# ---------------------------------------------------------------------------
# State Definition
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """LangGraph state representation for KubeCoach agent workflow."""

    session_id: str
    question: str
    messages: List[Dict[str, Any]]
    current_step: str
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    pending_tool: Optional[Dict[str, Any]]
    approval_required: bool
    approved: Optional[bool]
    final_answer: str
    error: Optional[str]


# ---------------------------------------------------------------------------
# In-Memory Session / Checkpoint Store
# ---------------------------------------------------------------------------

_SESSION_MEMORY: Dict[str, AgentState] = {}


def get_session_state(session_id: str) -> Optional[AgentState]:
    """Retrieve existing session state by session_id."""
    return _SESSION_MEMORY.get(session_id)


def save_session_state(session_id: str, state: AgentState) -> None:
    """Persist session state in memory."""
    _SESSION_MEMORY[session_id] = copy.deepcopy(state)


def clear_session_memory() -> None:
    """Clear in-memory session store (primarily for unit testing)."""
    _SESSION_MEMORY.clear()


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------

def reasoner_node(state: AgentState) -> AgentState:
    """Reasoner node: Analyzes user query, prior history, and decides next step."""
    question = state.get("question", "")
    history = state.get("messages", [])

    logger.info("Reasoner evaluating query: '%s'", question)
    state["current_step"] = "reasoner"

    # Check if a pending tool is already awaiting approval from a previous turn
    if state.get("pending_tool") and state.get("approved") is not None:
        logger.info("Reasoner resuming with approved=%s for pending tool", state.get("approved"))
        return state

    decision = _detect_tool_call_intent(question, history)

    if decision:
        tool_name, tool_args = decision
        tool_call_dict = {
            "name": tool_name,
            "arguments": tool_args,
        }
        state["tool_calls"] = state.get("tool_calls", []) + [tool_call_dict]
        state["messages"] = state.get("messages", []) + [
            {"role": "assistant", "type": "tool_call", "tool": tool_name, "arguments": tool_args}
        ]
        logger.info("Reasoner selected tool: %s", tool_name)
    else:
        # No tool needed, synthesize direct answer
        state["tool_calls"] = state.get("tool_calls", [])
        logger.info("Reasoner decided on direct answer (no tools required).")

    return state


def approval_gate_node(state: AgentState) -> AgentState:
    """Approval Gate node: Enforces Human-in-the-Loop approval for sensitive operations.

    Specifically, the project-card assigned tool `k8s_quantity_converter` requires
    human verification before execution. Safe read-only documentation tools like
    `k8s_rag_search` execute without pausing.
    """
    state["current_step"] = "approval_gate"
    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        state["approval_required"] = False
        return state

    latest_tool = tool_calls[-1]
    tool_name = latest_tool.get("name")
    tool_args = latest_tool.get("arguments", {})

    # Check if this tool requires human approval
    requires_approval = (tool_name == "k8s_quantity_converter")

    if not requires_approval:
        state["approval_required"] = False
        state["pending_tool"] = None
        logger.info("Tool '%s' does not require human approval. Proceeding directly.", tool_name)
        return state

    # Tool requires approval: check user's approval status
    approved_flag = state.get("approved")

    if approved_flag is None:
        # Pause workflow: wait for human approval
        state["approval_required"] = True
        state["pending_tool"] = latest_tool
        state["final_answer"] = (
            f"Human approval required: Tool '{tool_name}' is requesting to execute with arguments "
            f"{json.dumps(tool_args)}. Please submit your approval (approved=true/false) to proceed."
        )
        logger.info("Approval required for tool '%s'. Workflow paused.", tool_name)
    elif approved_flag is False:
        # Rejected by human
        state["approval_required"] = False
        state["pending_tool"] = None
        state["final_answer"] = f"Execution of tool '{tool_name}' was rejected by user."
        state["messages"] = state.get("messages", []) + [
            {"role": "system", "type": "approval_rejected", "tool": tool_name}
        ]
        logger.info("Tool '%s' was rejected by user.", tool_name)
    else:
        # Approved by human (approved_flag is True)
        state["approval_required"] = False
        state["pending_tool"] = None
        logger.info("Tool '%s' approved by user. Proceeding to execution.", tool_name)

    return state


def tool_executor_node(state: AgentState) -> AgentState:
    """Tool Executor node: Safely runs the tool and stores observations in state."""
    state["current_step"] = "tool_executor"
    tool_calls = state.get("tool_calls", [])
    if not tool_calls:
        return state

    latest_tool = tool_calls[-1]
    tool_name = latest_tool.get("name")
    tool_args = latest_tool.get("arguments", {})

    logger.info("Executing approved tool '%s' with args %s", tool_name, tool_args)
    observation = execute_tool(tool_name, tool_args)

    results = state.get("tool_results", [])
    results.append({"tool": tool_name, "arguments": tool_args, "result": observation})
    state["tool_results"] = results

    # Record observation in messages
    state["messages"] = state.get("messages", []) + [
        {
            "role": "system",
            "type": "observation",
            "tool": tool_name,
            "content": json.dumps(observation),
        }
    ]

    # Collect citations if RAG tool was invoked
    if tool_name == "k8s_rag_search" and observation.get("success"):
        citations = state.get("citations", [])
        citations.extend(observation.get("citations", []))
        state["citations"] = citations

    return state


def synthesizer_node(state: AgentState) -> AgentState:
    """Synthesizer node: Compiles the final response from tool observations or direct LLM."""
    state["current_step"] = "synthesizer"

    # If approval is still required or was rejected, preserve the message
    if state.get("approval_required"):
        return state
    if state.get("approved") is False:
        return state

    tool_results = state.get("tool_results", [])

    if not tool_results:
        # Direct response without tools
        question = state.get("question", "")
        resp = generate_chat_response(question)
        state["final_answer"] = resp.get("answer", "I could not find an answer in official Kubernetes documentation.")
        return state

    answer_sections: List[str] = []
    for item in tool_results:
        tool = item.get("tool")
        res = item.get("result", {})
        if tool == "k8s_quantity_converter":
            if res.get("success"):
                answer_sections.append(res.get("explanation", ""))
            else:
                answer_sections.append(f"Quantity conversion failed: {res.get('error')}")
        elif tool == "k8s_rag_search":
            if res.get("success"):
                answer_sections.append(res.get("answer", ""))
            else:
                answer_sections.append(f"Documentation search failed: {res.get('error')}")
        else:
            if not res.get("success"):
                answer_sections.append(f"Tool '{tool}' error: {res.get('error')}")

    state["final_answer"] = "\n\n".join(answer_sections)
    return state


# ---------------------------------------------------------------------------
# Routing Logic (Conditional Edges)
# ---------------------------------------------------------------------------

def route_reasoner(state: AgentState) -> str:
    """Route from reasoner: decide whether to invoke approval gate or synthesizer/END."""
    # If resuming a pending approval
    if state.get("pending_tool") and state.get("approved") is not None:
        return "approval_gate"

    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        return "approval_gate"
    return "synthesizer"


def route_approval_gate(state: AgentState) -> str:
    """Route from approval gate: check if approval is required, rejected, or granted."""
    if state.get("approval_required"):
        return END
    if state.get("approved") is False:
        return END
    return "tool_executor"


# ---------------------------------------------------------------------------
# Graph Builder & Runner
# ---------------------------------------------------------------------------

class CompiledKubeCoachGraph:
    """Lightweight, resilient stateful graph runner adhering to LangGraph specification."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Callable[[AgentState], AgentState]] = {
            "reasoner": reasoner_node,
            "approval_gate": approval_gate_node,
            "tool_executor": tool_executor_node,
            "synthesizer": synthesizer_node,
        }

    def invoke(self, state: AgentState) -> AgentState:
        """Execute state through graph edges until END is reached."""
        current_state = copy.deepcopy(state)

        # 1. Entry point: Reasoner
        current_state = self.nodes["reasoner"](current_state)

        # 2. Conditional edge: Reasoner -> Approval Gate or Synthesizer
        next_step = route_reasoner(current_state)

        if next_step == "approval_gate":
            current_state = self.nodes["approval_gate"](current_state)
            gate_next = route_approval_gate(current_state)

            if gate_next == "tool_executor":
                current_state = self.nodes["tool_executor"](current_state)
                # Tool Executor -> Synthesizer
                current_state = self.nodes["synthesizer"](current_state)
            elif gate_next == END:
                # Workflow paused for approval or rejected
                return current_state
        elif next_step == "synthesizer":
            current_state = self.nodes["synthesizer"](current_state)

        return current_state


_COMPILED_GRAPH = CompiledKubeCoachGraph()


def get_agent_graph() -> CompiledKubeCoachGraph:
    """Retrieve compiled graph singleton."""
    return _COMPILED_GRAPH


# ---------------------------------------------------------------------------
# Public Entry Function: run_agent
# ---------------------------------------------------------------------------

def run_agent(
    question: str,
    session_id: Optional[str] = None,
    approved: Optional[bool] = None,
) -> Dict[str, Any]:
    """Execute the stateful KubeCoach agent workflow.

    Args:
        question: User query or instruction.
        session_id: Optional persistent session ID for multi-turn conversation memory.
        approved: Optional user approval flag (True/False/None) for pending operations.

    Returns:
        Structured response dictionary containing answer, citations, tool_calls,
        session_id, approval_required, and status.
    """
    sid = session_id.strip() if session_id and session_id.strip() else f"sess-{uuid.uuid4().hex[:8]}"

    # Load existing state from conversation memory if present
    existing_state = get_session_state(sid)

    if existing_state:
        state = copy.deepcopy(existing_state)
        state["session_id"] = sid
        # Append user question to history
        if question and question.strip():
            state["question"] = question.strip()
            state["messages"] = state.get("messages", []) + [{"role": "user", "content": question.strip()}]
        if approved is not None:
            state["approved"] = approved
    else:
        state = AgentState(
            session_id=sid,
            question=question.strip() if question else "",
            messages=[{"role": "user", "content": question.strip()}] if question else [],
            current_step="init",
            tool_calls=[],
            tool_results=[],
            citations=[],
            pending_tool=None,
            approval_required=False,
            approved=approved,
            final_answer="",
            error=None,
        )

    # Run graph execution
    graph = get_agent_graph()
    updated_state = graph.invoke(state)

    # Persist updated session in memory
    save_session_state(sid, updated_state)

    approval_status = None
    if updated_state.get("approval_required"):
        approval_status = "pending"
    elif updated_state.get("approved") is False:
        approval_status = "rejected"
    elif updated_state.get("approved") is True:
        approval_status = "approved"

    return {
        "question": question,
        "answer": updated_state.get("final_answer", ""),
        "tool_calls": updated_state.get("tool_calls", []),
        "citations": updated_state.get("citations", []),
        "session_id": sid,
        "approval_required": updated_state.get("approval_required", False),
        "approval_status": approval_status,
        "pending_tool": updated_state.get("pending_tool"),
        "success": True,
    }
