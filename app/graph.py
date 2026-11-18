"""
app/graph.py - Production-Quality LangGraph Stateful Agent Workflow (Day 9)

Implements the KubeCoach stateful AI agent using official LangGraph APIs:
- `StateGraph`, `START`, `END` (`langgraph.graph`)
- `MemorySaver` (`langgraph.checkpoint.memory`) for persistent, session-isolated conversation memory
- `interrupt` and `Command` (`langgraph.types`) for Human-in-the-Loop (HITL) approval

Graph Flow:
    START -> reasoning_node
        - k8s_rag_search        -> tool_execution_node -> reasoning_node -> final_response_node -> END
        - k8s_quantity_converter -> approval_node (interrupt/resume)
            - approved=True     -> tool_execution_node -> reasoning_node -> final_response_node -> END
            - approved=False    -> final_response_node -> END (tool NOT executed)
        - direct / done         -> final_response_node -> END
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agent_loop import (
    PlannerFn,
    _deduplicate_citations,
    _synthesize_answer_from_observations,
    plan_next_action,
)
from app.tools import execute_tool

logger = logging.getLogger("kubecoach.graph")

TOOLS_REQUIRING_APPROVAL = {"k8s_quantity_converter"}


# ---------------------------------------------------------------------------
# LangGraph State Schema
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    """Typed state passed across all LangGraph nodes and persisted in MemorySaver."""

    question: str
    messages: List[Dict[str, Any]]
    session_id: str
    selected_tool: Optional[str]
    tool_arguments: Dict[str, Any]
    tool_output: Optional[Dict[str, Any]]
    tool_execution_history: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    approval_status: str
    pending_tool: Optional[Dict[str, Any]]
    final_answer: str
    iteration_count: int
    max_iterations: int
    execution_trace: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Graph Construction Factory (Nodes, Conditional Edges & MemorySaver)
# ---------------------------------------------------------------------------

def build_agent_graph(
    checkpointer: Optional[MemorySaver] = None,
    planner_fn: Optional[PlannerFn] = None,
) -> Any:
    """Compile the KubeCoach LangGraph StateGraph with MemorySaver checkpointing.

    Args:
        checkpointer: LangGraph checkpointer instance (defaults to new `MemorySaver()`).
        planner_fn: Optional injectable planner callable `(question, history) -> decision_dict`
            for deterministic unit tests with mocked LLM responses.

    Returns:
        Compiled LangGraph runnable supporting `.invoke(...)` and `.get_state(config)`.
    """
    active_checkpointer = checkpointer if checkpointer is not None else MemorySaver()
    active_planner: PlannerFn = planner_fn or (lambda q, h: plan_next_action(q, h))

    # --- Node 1: reasoning_node ---
    def reasoning_node(state: AgentState) -> Dict[str, Any]:
        """Inspect user query, conversation history, and observations to choose next action."""
        question = state.get("question", "").strip()
        iteration_count = int(state.get("iteration_count", 0))
        max_iterations = int(state.get("max_iterations", 5))
        tool_history = list(state.get("tool_execution_history", []))
        messages = list(state.get("messages", []))
        trace = list(state.get("execution_trace", []))

        # Guard against infinite loops
        if iteration_count >= max_iterations:
            logger.warning(
                "Session '%s' reached max_iterations=%d in reasoning_node.",
                state.get("session_id"),
                max_iterations,
            )
            trace.append({
                "step": iteration_count,
                "node": "reasoning_node",
                "action": "iteration_limit",
                "detail": f"Reached maximum iteration limit ({max_iterations}).",
            })
            return {
                "selected_tool": None,
                "tool_arguments": {},
                "execution_trace": trace,
            }

        next_iter = iteration_count + 1

        # Build planner context: prior conversation messages + current-turn observations
        planner_history: List[Dict[str, Any]] = [
            m for m in messages if m.get("role") in ("user", "assistant")
        ]
        for entry in tool_history:
            planner_history.append({
                "type": "observation",
                "step": entry.get("step"),
                "tool": entry.get("tool"),
                "result": entry.get("result", {}),
            })

        try:
            decision = active_planner(question, planner_history)
        except Exception as exc:
            logger.error("Planner error in reasoning_node: %s", exc)
            trace.append({
                "step": next_iter,
                "node": "reasoning_node",
                "action": "error",
                "detail": f"Reasoning error: {exc}",
            })
            return {
                "iteration_count": next_iter,
                "selected_tool": None,
                "tool_arguments": {},
                "final_answer": f"Agent reasoning failed safely: {exc}",
                "execution_trace": trace,
            }

        action = str(decision.get("action", "")).strip().lower()
        thought = str(decision.get("thought", ""))

        if action == "tool_call" and decision.get("tool"):
            tool_name = str(decision["tool"]).strip()
            tool_args = decision.get("arguments", {})
            if not isinstance(tool_args, dict):
                tool_args = {}

            logger.info(
                "Session '%s' reasoning_node (iter %d) selected tool '%s' with args %s",
                state.get("session_id"),
                next_iter,
                tool_name,
                tool_args,
            )
            trace.append({
                "step": next_iter,
                "node": "reasoning_node",
                "action": "tool_call",
                "tool": tool_name,
                "arguments": tool_args,
                "thought": thought,
            })
            return {
                "iteration_count": next_iter,
                "selected_tool": tool_name,
                "tool_arguments": tool_args,
                "pending_tool": (
                    {"tool": tool_name, "arguments": tool_args}
                    if tool_name in TOOLS_REQUIRING_APPROVAL
                    else None
                ),
                "execution_trace": trace,
            }

        # Direct or synthesized final answer
        proposed_answer = str(decision.get("answer", "")).strip()
        trace.append({
            "step": next_iter,
            "node": "reasoning_node",
            "action": "final_answer",
            "thought": thought,
        })
        return {
            "iteration_count": next_iter,
            "selected_tool": None,
            "tool_arguments": {},
            "pending_tool": None,
            "final_answer": proposed_answer,
            "execution_trace": trace,
        }

    # --- Node 2: approval_node (Official LangGraph interrupt/resume) ---
    def approval_node(state: AgentState) -> Dict[str, Any]:
        """Pause graph execution using LangGraph `interrupt()` for human approval."""
        tool_name = state.get("selected_tool") or "unknown"
        tool_args = dict(state.get("tool_arguments", {}))
        trace = list(state.get("execution_trace", []))
        step = int(state.get("iteration_count", 1))

        approval_request_payload = {
            "type": "human_approval_required",
            "tool": tool_name,
            "arguments": tool_args,
            "message": (
                f"Human approval required before executing '{tool_name}' "
                f"with arguments {json.dumps(tool_args)}. "
                "Respond with approved=true to execute or approved=false to reject."
            ),
        }

        logger.info(
            "Session '%s' pausing at approval_node for tool '%s' with args %s",
            state.get("session_id"),
            tool_name,
            tool_args,
        )

        # Official LangGraph interrupt: suspends execution and checkpoints state in MemorySaver
        human_decision = interrupt(approval_request_payload)

        if isinstance(human_decision, dict):
            is_approved = bool(human_decision.get("approved", False))
        else:
            is_approved = bool(human_decision)

        if is_approved:
            logger.info("Session '%s' human approval GRANTED for tool '%s'.", state.get("session_id"), tool_name)
            trace.append({
                "step": step,
                "node": "approval_node",
                "tool": tool_name,
                "arguments": tool_args,
                "decision": "approved",
            })
            return {
                "approval_status": "approved",
                "pending_tool": None,
                "execution_trace": trace,
            }

        logger.info("Session '%s' human approval REJECTED for tool '%s'.", state.get("session_id"), tool_name)
        rejection_msg = (
            f"Execution of tool '{tool_name}' with arguments {json.dumps(tool_args)} "
            "was rejected by the user. The tool was not executed."
        )
        trace.append({
            "step": step,
            "node": "approval_node",
            "tool": tool_name,
            "arguments": tool_args,
            "decision": "rejected",
        })
        return {
            "approval_status": "rejected",
            "selected_tool": None,
            "tool_arguments": {},
            "pending_tool": None,
            "final_answer": rejection_msg,
            "execution_trace": trace,
        }

    # --- Node 3: tool_execution_node ---
    def tool_execution_node(state: AgentState) -> Dict[str, Any]:
        """Validate and execute the approved/safe registered tool, then return observation."""
        tool_name = str(state.get("selected_tool") or "").strip()
        tool_args = dict(state.get("tool_arguments", {}))
        step = int(state.get("iteration_count", 1))
        tool_history = list(state.get("tool_execution_history", []))
        citations = list(state.get("citations", []))
        trace = list(state.get("execution_trace", []))

        logger.info(
            "Session '%s' executing tool '%s' with args %s",
            state.get("session_id"),
            tool_name,
            tool_args,
        )
        observation = execute_tool(tool_name, tool_args)

        history_entry = {
            "step": step,
            "tool": tool_name,
            "arguments": tool_args,
            "result": observation,
            "success": bool(observation.get("success", False)),
        }
        tool_history.append(history_entry)

        if tool_name == "k8s_rag_search" and observation.get("success"):
            citations.extend(observation.get("citations", []))

        trace.append({
            "step": step,
            "node": "tool_execution_node",
            "tool": tool_name,
            "arguments": tool_args,
            "success": bool(observation.get("success", False)),
            "citations_count": len(observation.get("citations", [])) if tool_name == "k8s_rag_search" else 0,
        })

        return {
            "tool_output": observation,
            "tool_execution_history": tool_history,
            "citations": _deduplicate_citations(citations),
            "selected_tool": None,
            "tool_arguments": {},
            "execution_trace": trace,
        }

    # --- Node 4: final_response_node ---
    def final_response_node(state: AgentState) -> Dict[str, Any]:
        """Compile final grounded answer and persist assistant turn into conversation memory."""
        question = state.get("question", "")
        approval_status = state.get("approval_status", "not_required")
        tool_history = list(state.get("tool_execution_history", []))
        messages = list(state.get("messages", []))
        trace = list(state.get("execution_trace", []))
        final_answer = str(state.get("final_answer", "")).strip()

        if approval_status == "rejected":
            if not final_answer:
                final_answer = "Tool execution was rejected by the user."
        elif not final_answer:
            obs_formatted = [
                {"tool": h.get("tool"), "result": h.get("result", {})}
                for h in tool_history
            ]
            final_answer = _synthesize_answer_from_observations(question, obs_formatted)

        messages.append({"role": "assistant", "content": final_answer})
        trace.append({
            "step": int(state.get("iteration_count", 0)),
            "node": "final_response_node",
            "status": "completed",
            "approval_status": approval_status,
        })

        return {
            "final_answer": final_answer,
            "messages": messages,
            "citations": _deduplicate_citations(list(state.get("citations", []))),
            "execution_trace": trace,
        }

    # --- Conditional Routing Functions ---
    def route_after_reasoning(state: AgentState) -> str:
        """Route from reasoning_node to approval_node, tool_execution_node, or final_response_node."""
        selected = state.get("selected_tool")
        if not selected:
            return "final_response_node"
        if selected in TOOLS_REQUIRING_APPROVAL:
            return "approval_node"
        return "tool_execution_node"

    def route_after_approval(state: AgentState) -> str:
        """Route from approval_node to tool_execution_node if approved, else final_response_node."""
        if state.get("approval_status") == "approved":
            return "tool_execution_node"
        return "final_response_node"

    # --- Wire StateGraph ---
    workflow = StateGraph(AgentState)
    workflow.add_node("reasoning_node", reasoning_node)
    workflow.add_node("approval_node", approval_node)
    workflow.add_node("tool_execution_node", tool_execution_node)
    workflow.add_node("final_response_node", final_response_node)

    workflow.add_edge(START, "reasoning_node")
    workflow.add_conditional_edges(
        "reasoning_node",
        route_after_reasoning,
        {
            "approval_node": "approval_node",
            "tool_execution_node": "tool_execution_node",
            "final_response_node": "final_response_node",
        },
    )
    workflow.add_conditional_edges(
        "approval_node",
        route_after_approval,
        {
            "tool_execution_node": "tool_execution_node",
            "final_response_node": "final_response_node",
        },
    )
    workflow.add_edge("tool_execution_node", "reasoning_node")
    workflow.add_edge("final_response_node", END)

    return workflow.compile(checkpointer=active_checkpointer)


# ---------------------------------------------------------------------------
# Module-Level Singleton Graph & MemorySaver Checkpointer
# ---------------------------------------------------------------------------

_CHECKPOINTER = MemorySaver()
_COMPILED_GRAPH = build_agent_graph(checkpointer=_CHECKPOINTER)


def get_agent_graph() -> Any:
    """Return the compiled LangGraph singleton."""
    return _COMPILED_GRAPH


def reset_agent_memory() -> None:
    """Reset the singleton MemorySaver and recompile the default graph (for tests)."""
    global _CHECKPOINTER, _COMPILED_GRAPH
    _CHECKPOINTER = MemorySaver()
    _COMPILED_GRAPH = build_agent_graph(checkpointer=_CHECKPOINTER)


def clear_session_memory() -> None:
    """Alias for `reset_agent_memory()` for backward compatibility."""
    reset_agent_memory()


def get_session_state(session_id: str, graph: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Read the persisted state values for a thread/session from MemorySaver."""
    active_graph = graph or _COMPILED_GRAPH
    config = {"configurable": {"thread_id": session_id}}
    snapshot = active_graph.get_state(config)
    if snapshot and snapshot.values:
        return dict(snapshot.values)
    return None


def get_session_history(session_id: str, graph: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Return persisted conversation messages for a session from MemorySaver."""
    values = get_session_state(session_id, graph=graph)
    if not values:
        return []
    return list(values.get("messages", []))


def has_pending_approval(session_id: str, graph: Optional[Any] = None) -> bool:
    """Return True if the session is currently paused at an approval interrupt."""
    active_graph = graph or _COMPILED_GRAPH
    config = {"configurable": {"thread_id": session_id}}
    snapshot = active_graph.get_state(config)
    return bool(snapshot and snapshot.next)


# ---------------------------------------------------------------------------
# Public Entrypoints: run_agent & resume_agent_approval
# ---------------------------------------------------------------------------

def _extract_interrupt_payload(graph_output: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract interrupt value dict from LangGraph `__interrupt__` output if present."""
    interrupts = graph_output.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return value if isinstance(value, dict) else {"message": str(value)}


def _format_graph_response(
    question: str,
    session_id: str,
    raw_output: Dict[str, Any],
) -> Dict[str, Any]:
    """Normalize LangGraph output (completed or interrupted) into a consistent API contract."""
    interrupt_payload = _extract_interrupt_payload(raw_output)

    tool_calls = [
        {
            "step": item.get("step"),
            "tool": item.get("tool"),
            "arguments": item.get("arguments", {}),
            "success": item.get("success", False),
        }
        for item in raw_output.get("tool_execution_history", [])
    ]

    if interrupt_payload is not None:
        proposed_tool = {
            "tool": interrupt_payload.get("tool", raw_output.get("selected_tool")),
            "arguments": interrupt_payload.get("arguments", raw_output.get("tool_arguments", {})),
        }
        return {
            "question": question or raw_output.get("question", ""),
            "answer": interrupt_payload.get(
                "message",
                f"Human approval required before executing '{proposed_tool['tool']}'.",
            ),
            "tool_calls": tool_calls,
            "citations": raw_output.get("citations", []),
            "session_id": session_id,
            "approval_required": True,
            "approval_status": "pending",
            "pending_tool": proposed_tool,
            "execution_trace": raw_output.get("execution_trace", []),
            "iteration_count": raw_output.get("iteration_count", 0),
            "success": True,
        }

    return {
        "question": question or raw_output.get("question", ""),
        "answer": raw_output.get("final_answer", ""),
        "tool_calls": tool_calls,
        "citations": raw_output.get("citations", []),
        "session_id": session_id,
        "approval_required": False,
        "approval_status": raw_output.get("approval_status", "not_required"),
        "pending_tool": None,
        "execution_trace": raw_output.get("execution_trace", []),
        "iteration_count": raw_output.get("iteration_count", 0),
        "success": True,
    }


def resume_agent_approval(
    session_id: str,
    approved: bool,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """Resume a paused LangGraph execution with human approval or rejection.

    Args:
        session_id: Existing thread/session ID currently waiting at `approval_node`.
        approved: True to execute the proposed tool; False to reject cleanly without executing.
        graph: Optional compiled LangGraph instance (defaults to module singleton).

    Raises:
        ValueError: If `session_id` is empty or has no pending approval interrupt.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id must be a non-empty string.")

    sid = session_id.strip()
    active_graph = graph or _COMPILED_GRAPH
    config = {"configurable": {"thread_id": sid}}

    if not has_pending_approval(sid, graph=active_graph):
        raise ValueError(f"No pending human approval found for session_id '{sid}'.")

    prior_state = get_session_state(sid, graph=active_graph) or {}
    prior_question = prior_state.get("question", "")

    logger.info("Resuming paused session '%s' with approved=%s via LangGraph Command(resume).", sid, approved)
    output = active_graph.invoke(Command(resume={"approved": bool(approved)}), config=config)
    return _format_graph_response(prior_question, sid, output)


def run_agent(
    question: str,
    session_id: Optional[str] = None,
    approved: Optional[bool] = None,
    max_iterations: int = 5,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute or resume the KubeCoach LangGraph agent workflow.

    Supports:
    - Fresh queries with automatic or caller-supplied `session_id` (thread_id).
    - Multi-turn conversation persistence via LangGraph `MemorySaver`.
    - Interrupting before `k8s_quantity_converter` and resuming when `approved` is provided.

    Args:
        question: User query or follow-up message.
        session_id: Optional thread ID for persistent, isolated conversation memory.
        approved: Optional True/False human decision to resume an interrupted graph.
        max_iterations: Safety ceiling on reasoning loops per turn (default 5).
        graph: Optional compiled LangGraph instance (defaults to module singleton).

    Returns:
        Consistent response dictionary with answer, tool_calls, citations, session_id,
        approval_required, approval_status, pending_tool, and execution_trace.
    """
    active_graph = graph or _COMPILED_GRAPH
    sid = session_id.strip() if isinstance(session_id, str) and session_id.strip() else f"sess-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": sid}}

    # Case 1: Resuming an interrupted approval gate on this session
    if approved is not None and has_pending_approval(sid, graph=active_graph):
        return resume_agent_approval(session_id=sid, approved=bool(approved), graph=active_graph)

    clean_question = question.strip() if isinstance(question, str) else ""
    if not clean_question:
        raise ValueError("Question cannot be empty or whitespace only.")

    # Preserve prior conversation messages from MemorySaver across turns
    prior_messages = get_session_history(sid, graph=active_graph)
    updated_messages = prior_messages + [{"role": "user", "content": clean_question}]

    initial_state: AgentState = {
        "question": clean_question,
        "messages": updated_messages,
        "session_id": sid,
        "selected_tool": None,
        "tool_arguments": {},
        "tool_output": None,
        "tool_execution_history": [],
        "citations": [],
        "approval_status": "not_required",
        "pending_tool": None,
        "final_answer": "",
        "iteration_count": 0,
        "max_iterations": max(1, int(max_iterations)),
        "execution_trace": [],
    }

    output = active_graph.invoke(initial_state, config=config)
    response = _format_graph_response(clean_question, sid, output)

    # Convenience: if caller explicitly passed approved=True/False upfront on the same call
    if response["approval_required"] and approved is not None:
        return resume_agent_approval(session_id=sid, approved=bool(approved), graph=active_graph)

    return response


if __name__ == "__main__":
    r1 = run_agent("Convert 500m CPU to cores", session_id="cli-demo")
    print("Step 1 (Interrupted for approval):", json.dumps(r1, indent=2))
    r2 = resume_agent_approval(session_id="cli-demo", approved=True)
    print("Step 2 (Resumed after approval):", json.dumps(r2, indent=2))
