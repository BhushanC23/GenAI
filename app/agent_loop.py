"""
app/agent_loop.py - Educational Autonomous Agent Loop (Day 9)

Implements a transparent, step-by-step agent loop:
1. User provides question.
2. Agent decides whether to call a tool or answer directly.
3. If tool called: agent validates and executes tool.
4. Tool observation is recorded in conversation history.
5. Loop repeats until final answer is synthesized or max_iterations reached.
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.llm import generate_chat_response
from app.tools import execute_tool, TOOL_SCHEMAS

logger = logging.getLogger("kubecoach.agent_loop")


def _detect_tool_call_intent(question: str, history: List[Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Inspect question and execution history to decide if an unexecuted tool is required.

    Returns:
        Tuple of (tool_name, arguments) or None if ready to answer.
    """
    already_executed = {h.get("tool") for h in history if h.get("type") == "observation"}

    # Pattern for resource conversion
    # E.g. '500m', '128Mi', '2Gi', 'convert 250m cpu', 'how many bytes in 1Gi'
    qty_match = re.search(r"\b([0-9]+(?:\.[0-9]+)?\s*(?:m|Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E|bytes?|cores?))\b", question, re.IGNORECASE)
    is_convert_intent = bool(re.search(r"\b(convert|conversion|quantity|millicores?|bytes?|how much|how many)\b", question, re.IGNORECASE))

    if (qty_match or is_convert_intent) and "k8s_quantity_converter" not in already_executed:
        raw_qty = qty_match.group(1) if qty_match else ""
        if not raw_qty:
            # fallback find bare numbers with unit words
            num_match = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*(cpu|m|cores?|mi|gi|ki|mb|gb)\b", question, re.IGNORECASE)
            if num_match:
                raw_qty = f"{num_match.group(1)}{num_match.group(2)}"
        if raw_qty:
            target_unit = None
            if re.search(r"\b(cores?|c)\b", question, re.IGNORECASE) and not raw_qty.lower().endswith("core"):
                target_unit = "cores"
            elif re.search(r"\b(millicores?|m)\b", question, re.IGNORECASE) and not raw_qty.lower().endswith("m"):
                target_unit = "m"
            elif re.search(r"\b(bytes?)\b", question, re.IGNORECASE):
                target_unit = "bytes"
            elif re.search(r"\b(mi|mib)\b", question, re.IGNORECASE) and not raw_qty.lower().endswith("mi"):
                target_unit = "Mi"
            elif re.search(r"\b(gi|gib)\b", question, re.IGNORECASE) and not raw_qty.lower().endswith("gi"):
                target_unit = "Gi"

            return ("k8s_quantity_converter", {"quantity": raw_qty.strip(), "target_unit": target_unit})

    # Pattern for Kubernetes documentation / concepts / kubectl search
    is_k8s_doc = bool(re.search(r"\b(what|how|why|describe|explain|list|pod|service|deployment|kubectl|daemonset|statefulset|ingress|namespace|secret|configmap)\b", question, re.IGNORECASE))
    if is_k8s_doc and "k8s_rag_search" not in already_executed:
        # Extract question query
        return ("k8s_rag_search", {"query": question.strip(), "top_k": 3})

    return None


def run_agent_loop(
    question: str,
    max_iterations: int = 5,
    custom_tool_call: Optional[Tuple[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run an educational autonomous agent loop.

    Flow:
    User Question -> LLM Reasoner -> Tool Execution -> Observation -> Final Synthesis.

    Args:
        question: User prompt or query.
        max_iterations: Safety limit for loop execution (default: 5).
        custom_tool_call: Optional explicit tool call to inject (useful for testing).

    Returns:
        Structured result containing answer, tool_calls, observations, citations, and iterations.
    """
    if not question or not isinstance(question, str) or not question.strip():
        return {
            "question": question,
            "answer": "Please ask a valid Kubernetes question or command inquiry.",
            "tool_calls": [],
            "observations": [],
            "citations": [],
            "iterations": 0,
            "success": False,
        }

    logger.info("Starting Agent Loop for question: '%s' (max_iterations=%d)", question.strip(), max_iterations)

    history: List[Dict[str, Any]] = [
        {"role": "user", "content": question.strip()}
    ]
    tool_calls: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []

    iterations = 0

    while iterations < max_iterations:
        iterations += 1
        logger.debug("Agent Loop iteration %d of %d", iterations, max_iterations)

        # Decide next step (Reasoning)
        if custom_tool_call and iterations == 1:
            decision = custom_tool_call
        else:
            decision = _detect_tool_call_intent(question, history)

        # If no tool is needed or all needed tools executed, synthesize final answer
        if not decision:
            logger.info("Agent Loop completed tool execution. Synthesizing final response.")
            break

        tool_name, tool_args = decision
        tool_call_record = {
            "step": iterations,
            "tool": tool_name,
            "arguments": tool_args,
        }
        tool_calls.append(tool_call_record)
        logger.info("Agent decided to invoke tool '%s' with args %s", tool_name, tool_args)

        # Execute Tool (Action)
        observation = execute_tool(tool_name, tool_args)
        obs_record = {
            "type": "observation",
            "step": iterations,
            "tool": tool_name,
            "result": observation,
        }
        observations.append(obs_record)
        history.append({
            "role": "system",
            "type": "observation",
            "tool": tool_name,
            "content": f"Observation from {tool_name}: {json.dumps(observation)}",
        })

        # Collect citations if RAG tool was called
        if tool_name == "k8s_rag_search" and observation.get("success"):
            citations.extend(observation.get("citations", []))

    # Check if max_iterations exceeded
    if iterations >= max_iterations and not observations:
        return {
            "question": question,
            "answer": f"Agent reached iteration limit ({max_iterations}) without reaching a conclusion.",
            "tool_calls": tool_calls,
            "observations": observations,
            "citations": citations,
            "iterations": iterations,
            "success": False,
        }

    # Final Answer Synthesis
    # Synthesize answers from observations
    answer_parts: List[str] = []

    for obs in observations:
        res = obs.get("result", {})
        tool = obs.get("tool")
        if tool == "k8s_quantity_converter":
            if res.get("success"):
                answer_parts.append(res.get("explanation", ""))
            else:
                answer_parts.append(f"Quantity conversion failed: {res.get('error')}")
        elif tool == "k8s_rag_search":
            if res.get("success"):
                rag_ans = res.get("answer", "")
                if rag_ans:
                    answer_parts.append(rag_ans)
            else:
                answer_parts.append(f"Documentation retrieval failed: {res.get('error')}")
        else:
            if not res.get("success"):
                answer_parts.append(f"Tool '{tool}' failed: {res.get('error')}")

    if not answer_parts:
        # No tools were invoked, answer directly using LLM
        direct_resp = generate_chat_response(question)
        final_answer = direct_resp.get("answer", "I could not find an answer in official Kubernetes documentation.")
    else:
        final_answer = "\n\n".join(answer_parts)

    return {
        "question": question,
        "answer": final_answer,
        "tool_calls": tool_calls,
        "observations": observations,
        "citations": citations,
        "iterations": iterations,
        "success": True,
    }
