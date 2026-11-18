"""
app/agent_loop.py - Hand-Written Autonomous Agent Loop for KubeCoach (Day 9)

Implements the explicit ReAct-style educational agent loop:
    Reason -> Select Tool -> Validate -> Execute -> Observe -> Reason Again -> Final Answer

Key Engineering Properties:
- Reuses the existing Day 6 LLM provider wrapper (`app/llm.py`) for reasoning.
- Executes ONLY registered tools validated against `TOOL_SCHEMAS` (`app/tools.py`).
- Preserves official Kubernetes citations from RAG tool observations.
- Enforces `max_iterations` to guarantee loop termination.
- Captures a structured `execution_trace` at every phase for debugging and viva explanation.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.llm import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    LLMError,
    call_gemini,
    call_groq,
    generate_chat_response,
)
from app.tools import TOOL_SCHEMAS, execute_tool, validate_tool_call

logger = logging.getLogger("kubecoach.agent_loop")

# Type alias for injectable/mockable planner function
PlannerFn = Callable[[str, List[Dict[str, Any]]], Dict[str, Any]]

# Regex for matching Kubernetes resource quantity tokens in natural language
_QTY_TOKEN_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9_.-])"
    r"([0-9]+(?:\.[0-9]+)?\s*(?:Ki|Mi|Gi|Ti|Pi|Ei|k|K|M|G|T|P|E|m|cores?|millicores?|bytes?))"
    r"(?![a-zA-Z0-9_])"
)

_AGENT_SYSTEM_PROMPT = (
    "You are KubeCoach, an educational Kubernetes AI agent. "
    "Decide whether to call one of the available tools or return a final answer.\n"
    f"Available tools (JSON schema):\n{json.dumps(TOOL_SCHEMAS, indent=2)}\n\n"
    "Always respond strictly in JSON with one of these two formats:\n"
    '1) {"action": "tool_call", "tool": "<tool_name>", "arguments": {...}, "thought": "<brief reason>"}\n'
    '2) {"action": "final_answer", "answer": "<grounded plain-English response>", "thought": "<brief reason>"}\n'
    "Never perform resource unit math yourself; always use k8s_quantity_converter."
)


def _extract_quantity_args(question: str) -> Optional[Dict[str, Any]]:
    """Deterministically extract quantity converter arguments from a user question."""
    text = question.strip()

    # Check explicit comparison phrasing first (e.g., "Compare 1Gi and 1G", "500m vs 1 core")
    is_comparison = bool(
        re.search(r"\b(compare|versus|vs\.?|larger|bigger|smaller|greater|less|difference between)\b", text, re.IGNORECASE)
    )
    tokens = [m.group(1).strip() for m in _QTY_TOKEN_PATTERN.finditer(text)]

    # Normalize bare numbers when paired with a known CPU/memory unit in comparisons (e.g., "Compare 500m vs 1")
    if is_comparison and len(tokens) == 1:
        bare_nums = re.findall(r"(?<![a-zA-Z0-9_.-])([0-9]+(?:\.[0-9]+)?)(?![a-zA-Z0-9_])", text)
        # Filter out numbers already part of tokens[0]
        first_num = re.match(r"^[0-9]+(?:\.[0-9]+)?", tokens[0])
        first_num_str = first_num.group(0) if first_num else ""
        other_nums = [n for n in bare_nums if n != first_num_str]
        if other_nums:
            tokens.append(other_nums[0])

    if is_comparison and len(tokens) >= 2:
        return {
            "quantity": tokens[0],
            "compare_to": tokens[1],
        }

    # Check single quantity conversion
    is_convert_intent = bool(
        re.search(
            r"\b(convert|conversion|quantity|millicores?|mebibytes?|gibibytes?|megabytes?|gigabytes?|bytes?|cpu|memory|cores?)\b",
            text,
            re.IGNORECASE,
        )
    )

    if tokens:
        raw_qty = tokens[0]
        # Clean descriptive words if user wrote "500m" or "2 cores"
        target_unit: Optional[str] = None

        # Detect explicit target unit phrasing: "to <unit>", "into <unit>", "in <unit>"
        target_match = re.search(
            r"\b(?:to|into|in)\s+(cores?|millicores?|m|bytes?|Ki|Mi|Gi|Ti|k|M|G|T|mebibytes?|gibibytes?)\b",
            text,
        )
        if target_match:
            raw_target = target_match.group(1)
            target_map = {
                "mebibyte": "Mi",
                "mebibytes": "Mi",
                "gibibyte": "Gi",
                "gibibytes": "Gi",
                "millicore": "m",
                "millicores": "m",
                "core": "cores",
                "cores": "cores",
                "byte": "bytes",
                "bytes": "bytes",
            }
            target_unit = target_map.get(raw_target.lower(), raw_target)
            # Avoid redundant target equal to source suffix when possible
            if raw_qty.endswith(target_unit) and target_unit not in ("cores", "bytes"):
                target_unit = None

        args: Dict[str, Any] = {"quantity": raw_qty}
        if target_unit:
            args["target_unit"] = target_unit
        return args

    # Fallback: "convert 2 CPU" where number has no suffix attached
    if is_convert_intent:
        bare_match = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:cpu)\b", text, re.IGNORECASE)
        if bare_match:
            return {"quantity": bare_match.group(1)}

    return None


def _synthesize_answer_from_observations(question: str, observations: List[Dict[str, Any]]) -> str:
    """Build a clear, grounded final answer strictly from observed tool results."""
    sections: List[str] = []

    for obs in observations:
        tool_name = obs.get("tool", "unknown")
        result = obs.get("result", {})

        if not result.get("success"):
            error_msg = result.get("error", "Unknown tool execution error.")
            sections.append(f"Tool '{tool_name}' could not complete the request: {error_msg}")
            continue

        if tool_name == "k8s_quantity_converter":
            explanation = result.get("explanation", "")
            target_conv = result.get("target_conversion")
            if target_conv:
                sections.append(f"{explanation} Converted value: {target_conv}.")
            else:
                sections.append(explanation)
        elif tool_name == "k8s_rag_search":
            rag_answer = result.get("answer", "")
            if rag_answer:
                sections.append(rag_answer)
        else:
            sections.append(str(result))

    if sections:
        return "\n\n".join(sections)

    # No tool observations collected: fall back to direct LLM response
    resp = generate_chat_response(question)
    return resp.get("answer", "I could not find an answer in the official Kubernetes documentation.")


def _deterministic_mock_planner(question: str, history: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic local planner used when no live LLM API key is configured.

    Demonstrates the full ReAct decision cycle cleanly and deterministically for
    offline development, grading, and automated unit tests.
    """
    observations = [h for h in history if h.get("type") == "observation"]
    executed_tools = {obs.get("tool") for obs in observations}

    # Check if quantity conversion is requested and not yet executed
    qty_args = _extract_quantity_args(question)
    if qty_args and "k8s_quantity_converter" not in executed_tools:
        return {
            "action": "tool_call",
            "tool": "k8s_quantity_converter",
            "arguments": qty_args,
            "thought": "Question involves Kubernetes CPU/Memory resource quantities; delegating deterministic math to k8s_quantity_converter.",
        }

    # Check if Kubernetes documentation search is requested and not yet executed
    is_k8s_doc_query = bool(
        re.search(
            r"\b(what|how|why|explain|describe|list|difference|kubectl|pod|pods|deployment|deployments|"
            r"service|services|ingress|configmap|secret|namespace|statefulset|daemonset|replicaset|"
            r"job|cronjob|pv|pvc|persistentvolume|role|rolebinding|serviceaccount|resourcequota|"
            r"crashloopbackoff|istio|mesh|restartpolicy|clusterip|nodeport)\b",
            question,
            re.IGNORECASE,
        )
    )
    # Only trigger RAG if it's genuinely asking about K8s docs (and not purely a quantity conversion like "What is 500m in cores?")
    pure_conversion_only = bool(qty_args) and not bool(
        re.search(
            r"\b(kubectl|pod|pods|deployment|service|ingress|configmap|secret|namespace|"
            r"statefulset|daemonset|replicaset|job|cronjob|persistentvolume|istio|restartpolicy)\b",
            question,
            re.IGNORECASE,
        )
    )

    if is_k8s_doc_query and not pure_conversion_only and "k8s_rag_search" not in executed_tools:
        return {
            "action": "tool_call",
            "tool": "k8s_rag_search",
            "arguments": {"query": question.strip(), "top_k": 3},
            "thought": "Question asks about Kubernetes concepts or kubectl commands; searching official documentation via k8s_rag_search.",
        }

    # All required tools have executed (or none needed) -> synthesize final answer
    final_text = _synthesize_answer_from_observations(question, observations)
    return {
        "action": "final_answer",
        "answer": final_text,
        "thought": "All necessary observations have been gathered; returning final grounded answer.",
    }


def _parse_llm_decision(raw_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse structured JSON decision returned by live LLM provider."""
    if not isinstance(raw_response, dict):
        return None
    action = str(raw_response.get("action", "")).strip().lower()
    if action == "tool_call" and raw_response.get("tool"):
        return {
            "action": "tool_call",
            "tool": str(raw_response["tool"]).strip(),
            "arguments": raw_response.get("arguments", {}),
            "thought": str(raw_response.get("thought", "Selected tool via LLM.")),
        }
    if action == "final_answer" and raw_response.get("answer"):
        return {
            "action": "final_answer",
            "answer": str(raw_response["answer"]).strip(),
            "thought": str(raw_response.get("thought", "Finalized answer via LLM.")),
        }
    return None


def plan_next_action(
    question: str,
    history: List[Dict[str, Any]],
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Reason about the current state and decide whether to call a tool or finalize.

    Uses the configured live LLM provider (`app/llm.py`) when valid credentials exist,
    falling back safely to `_deterministic_mock_planner` when running offline or in mock mode.
    """
    selected_provider = (provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)).lower()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    use_live_groq = selected_provider == "groq" and bool(groq_key) and not groq_key.startswith("gsk_your_groq")
    use_live_gemini = selected_provider == "gemini" and bool(gemini_key) and not gemini_key.startswith("AIzaSy_your_gemini")

    if not use_live_groq and not use_live_gemini:
        return _deterministic_mock_planner(question, history)

    history_summary = json.dumps(history[-6:], indent=2, default=str)
    prompt = (
        f"User Question: {question}\n\n"
        f"Recent Conversation & Tool Observations:\n{history_summary}\n\n"
        "Decide your next JSON action ('tool_call' or 'final_answer')."
    )

    try:
        if use_live_groq:
            raw = call_groq(
                prompt=prompt,
                system_prompt=_AGENT_SYSTEM_PROMPT,
                model=DEFAULT_GROQ_MODEL,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
                timeout=DEFAULT_TIMEOUT,
            )
        else:
            raw = call_gemini(
                prompt=prompt,
                system_prompt=_AGENT_SYSTEM_PROMPT,
                model=DEFAULT_GEMINI_MODEL,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
                timeout=DEFAULT_TIMEOUT,
            )

        # `call_groq`/`call_gemini` normalize to answer/confidence/follow_up; try parsing embedded JSON if present
        parsed = _parse_llm_decision(raw)
        if parsed:
            return parsed
        # Try parsing raw["answer"] as JSON if the wrapper nested it
        if isinstance(raw.get("answer"), str) and raw["answer"].strip().startswith("{"):
            try:
                nested = json.loads(raw["answer"])
                parsed_nested = _parse_llm_decision(nested)
                if parsed_nested:
                    return parsed_nested
            except json.JSONDecodeError:
                pass
    except LLMError as exc:
        logger.warning("Live LLM planner error (%s); falling back to deterministic planner.", exc)
    except Exception as exc:
        logger.warning("Unexpected planner error (%s); falling back to deterministic planner.", exc)

    return _deterministic_mock_planner(question, history)


def _deduplicate_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate RAG citations while preserving document_title, source_url, page, and chunk_id."""
    seen = set()
    unique: List[Dict[str, Any]] = []
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        key = (
            citation.get("document_title", ""),
            citation.get("source_url", ""),
            citation.get("page", ""),
        )
        if key not in seen:
            seen.add(key)
            unique.append(citation)
    return unique


def run_agent_loop(
    question: str,
    max_iterations: int = 5,
    planner_fn: Optional[PlannerFn] = None,
    provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the hand-written ReAct agent loop:

    Reason -> Select Tool -> Validate -> Execute -> Observe -> Reason Again -> Final Answer

    Args:
        question: User's Kubernetes question or quantity request.
        max_iterations: Maximum reasoning/action cycles allowed (prevents infinite loops).
        planner_fn: Optional custom/mocked planner callable `(question, history) -> decision_dict`.
        provider: Optional LLM provider override ('groq', 'gemini', 'mock').

    Returns:
        Structured dictionary with `answer`, `tool_calls`, `observations`, `citations`,
        `iterations`, `execution_trace`, `stopped_by_limit`, and `success`.
    """
    if not isinstance(question, str) or not question.strip():
        return {
            "question": question,
            "answer": "Please provide a non-empty Kubernetes question or resource quantity.",
            "tool_calls": [],
            "observations": [],
            "citations": [],
            "iterations": 0,
            "execution_trace": [{"step": 0, "phase": "validate_input", "status": "rejected", "detail": "Empty question"}],
            "stopped_by_limit": False,
            "success": False,
        }

    clean_question = question.strip()
    max_iters = max(1, int(max_iterations))
    active_planner = planner_fn or (lambda q, h: plan_next_action(q, h, provider=provider))

    logger.info("Starting hand-written agent loop for '%s' (max_iterations=%d)", clean_question, max_iters)

    history: List[Dict[str, Any]] = [{"role": "user", "content": clean_question}]
    tool_calls: List[Dict[str, Any]] = []
    observations: List[Dict[str, Any]] = []
    citations: List[Dict[str, Any]] = []
    execution_trace: List[Dict[str, Any]] = []

    iterations = 0
    final_answer: Optional[str] = None
    stopped_by_limit = False

    while iterations < max_iters:
        iterations += 1

        # 1. REASON
        try:
            decision = active_planner(clean_question, history)
        except Exception as exc:
            logger.error("Planner failed at iteration %d: %s", iterations, exc)
            execution_trace.append({
                "step": iterations,
                "phase": "reason",
                "status": "error",
                "detail": f"Planner error: {exc}",
            })
            return {
                "question": clean_question,
                "answer": f"Agent reasoning failed due to a provider error: {exc}",
                "tool_calls": tool_calls,
                "observations": observations,
                "citations": _deduplicate_citations(citations),
                "iterations": iterations,
                "execution_trace": execution_trace,
                "stopped_by_limit": False,
                "success": False,
            }

        action = str(decision.get("action", "")).strip().lower()
        thought = str(decision.get("thought", ""))
        execution_trace.append({
            "step": iterations,
            "phase": "reason",
            "action": action,
            "thought": thought,
        })

        # 2. FINAL ANSWER CHECK
        if action == "final_answer":
            final_answer = str(decision.get("answer", "")).strip() or _synthesize_answer_from_observations(
                clean_question, observations
            )
            execution_trace.append({
                "step": iterations,
                "phase": "final_answer",
                "status": "completed",
            })
            break

        if action != "tool_call":
            execution_trace.append({
                "step": iterations,
                "phase": "reason",
                "status": "invalid_action",
                "detail": f"Unsupported agent action '{action}'",
            })
            final_answer = _synthesize_answer_from_observations(clean_question, observations)
            break

        # 3. SELECT TOOL
        tool_name = str(decision.get("tool", "")).strip()
        tool_args = decision.get("arguments", {})
        execution_trace.append({
            "step": iterations,
            "phase": "select_tool",
            "tool": tool_name,
            "arguments": tool_args,
        })

        # 4. VALIDATE TOOL & ARGUMENTS
        is_valid, validation_error = validate_tool_call(tool_name, tool_args)
        if not is_valid:
            logger.warning("Iteration %d validation failed for '%s': %s", iterations, tool_name, validation_error)
            error_obs = {
                "tool": tool_name,
                "error": validation_error,
                "success": False,
            }
            tool_calls.append({"step": iterations, "tool": tool_name, "arguments": tool_args, "valid": False})
            obs_entry = {"type": "observation", "step": iterations, "tool": tool_name, "result": error_obs}
            observations.append(obs_entry)
            history.append(obs_entry)
            execution_trace.append({
                "step": iterations,
                "phase": "validate",
                "tool": tool_name,
                "status": "failed",
                "error": validation_error,
            })
            continue

        execution_trace.append({
            "step": iterations,
            "phase": "validate",
            "tool": tool_name,
            "status": "passed",
        })

        # 5. EXECUTE REGISTERED TOOL
        tool_calls.append({"step": iterations, "tool": tool_name, "arguments": tool_args, "valid": True})
        observation_result = execute_tool(tool_name, tool_args)

        execution_trace.append({
            "step": iterations,
            "phase": "execute",
            "tool": tool_name,
            "success": bool(observation_result.get("success", False)),
        })

        # 6. OBSERVE
        obs_entry = {
            "type": "observation",
            "step": iterations,
            "tool": tool_name,
            "result": observation_result,
        }
        observations.append(obs_entry)
        history.append(obs_entry)

        if tool_name == "k8s_rag_search" and observation_result.get("success"):
            citations.extend(observation_result.get("citations", []))

        execution_trace.append({
            "step": iterations,
            "phase": "observe",
            "tool": tool_name,
            "success": bool(observation_result.get("success", False)),
            "citations_added": len(observation_result.get("citations", [])) if tool_name == "k8s_rag_search" else 0,
        })
    else:
        # Loop terminated by max_iterations without reaching final_answer
        stopped_by_limit = True
        logger.warning("Agent loop hit max_iterations=%d for '%s'.", max_iters, clean_question)
        execution_trace.append({
            "step": iterations,
            "phase": "iteration_limit",
            "status": "stopped",
            "detail": f"Reached maximum iteration limit ({max_iters}).",
        })

    if final_answer is None:
        if observations:
            synthesized = _synthesize_answer_from_observations(clean_question, observations)
            if stopped_by_limit:
                final_answer = f"{synthesized}\n\n(Note: Agent reached the maximum iteration limit of {max_iters}.)"
            else:
                final_answer = synthesized
        else:
            final_answer = f"Agent stopped after reaching the maximum iteration limit ({max_iters})."

    return {
        "question": clean_question,
        "answer": final_answer,
        "tool_calls": tool_calls,
        "observations": observations,
        "citations": _deduplicate_citations(citations),
        "iterations": iterations,
        "execution_trace": execution_trace,
        "stopped_by_limit": stopped_by_limit,
        "success": not (stopped_by_limit and not any(o["result"].get("success") for o in observations)),
    }


if __name__ == "__main__":
    demo = run_agent_loop("Compare 1Gi and 1G memory in Kubernetes")
    print(json.dumps(demo, indent=2))
