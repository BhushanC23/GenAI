"""
app/tools.py - KubeCoach Agent Tools and Registry (Day 9)

Implements safe, read-only tools for the KubeCoach AI Agent:
1. `k8s_rag_search`: Retrieval-Augmented Generation over official Kubernetes docs.
2. `k8s_quantity_converter`: Project-card assigned developer tool for converting
   Kubernetes CPU and Memory quantity representations (millicores, cores, Ki, Mi, Gi, etc.).
"""

from __future__ import annotations
import logging
import math
import re
from typing import Any, Dict, List, Optional, Union

from app.rag import execute_rag_pipeline

logger = logging.getLogger("kubecoach.tools")

# ---------------------------------------------------------------------------
# Tool 1: k8s_quantity_converter (Project Card Tool: SJ-58 Developer Tools)
# ---------------------------------------------------------------------------

# Kubernetes memory multipliers based on official documentation:
# https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#meaning-of-memory
MEMORY_BINARY_MULTIPLIERS = {
    "ki": 1024,
    "mi": 1024**2,
    "gi": 1024**3,
    "ti": 1024**4,
    "pi": 1024**5,
    "ei": 1024**6,
}

MEMORY_DECIMAL_MULTIPLIERS = {
    "k": 1000,
    "m": 1000**2,
    "g": 1000**3,
    "t": 1000**4,
    "p": 1000**5,
    "e": 1000**6,
}


def _parse_cpu_quantity(quantity: str, target_unit: Optional[str] = None) -> Dict[str, Any]:
    """Parse and convert a Kubernetes CPU quantity (cores or millicores)."""
    cleaned = quantity.strip().rstrip("sS").rstrip("coreCORE").strip()

    if cleaned.endswith("m") or cleaned.endswith("M"):
        # Millicores: e.g., "500m"
        val_str = cleaned[:-1].strip()
        try:
            millicores = float(val_str)
        except ValueError:
            raise ValueError(f"Invalid numeric value in CPU quantity '{quantity}'")
        cores = millicores / 1000.0
    else:
        # Whole or fractional cores: e.g., "1", "0.5", "2"
        try:
            cores = float(cleaned)
        except ValueError:
            raise ValueError(f"Invalid numeric value in CPU quantity '{quantity}'")
        millicores = cores * 1000.0

    if cores < 0 or millicores < 0:
        raise ValueError(f"CPU quantity cannot be negative: '{quantity}'")
    if cores > 10_000_000:
        raise ValueError(f"CPU quantity exceeds maximum reasonable cluster bound (10,000,000 cores): '{quantity}'")

    # Format cleanly
    millicores_int = int(round(millicores)) if abs(millicores - round(millicores)) < 1e-6 else round(millicores, 3)
    cores_clean = int(cores) if cores.is_integer() else round(cores, 4)

    representations = {
        "cores": cores_clean,
        "millicores": f"{millicores_int}m",
        "millicores_numeric": millicores_int,
    }

    target_converted = None
    if target_unit:
        tu = target_unit.strip().lower()
        if tu in ("m", "milli", "millicore", "millicores"):
            target_converted = f"{millicores_int}m"
        elif tu in ("c", "core", "cores"):
            target_converted = f"{cores_clean} cores"
        else:
            target_converted = f"{cores_clean} cores ({millicores_int}m)"

    explanation = (
        f"{quantity} CPU is equivalent to {cores_clean} core(s) ({millicores_int} millicores). "
        f"In Kubernetes, 1 CPU core equals 1000m (1000 millicores). "
        f"A container requesting {quantity} is allocated {cores_clean} hyperthread(s)/CPU share(s)."
    )

    return {
        "tool": "k8s_quantity_converter",
        "input": quantity,
        "resource_type": "cpu",
        "canonical_value": f"{cores_clean} cores",
        "representations": representations,
        "target_conversion": target_converted,
        "explanation": explanation,
        "success": True,
    }


def _parse_memory_quantity(quantity: str, target_unit: Optional[str] = None) -> Dict[str, Any]:
    """Parse and convert a Kubernetes Memory quantity (bytes, Ki, Mi, Gi, Ti, K, M, G, etc.)."""
    cleaned = quantity.strip().rstrip("bB").strip()

    # Pattern: optional sign, digits/floats, optional suffix
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?$", cleaned)
    if not match:
        raise ValueError(
            f"Invalid Kubernetes memory quantity format: '{quantity}'. "
            f"Expected examples: '128Mi', '2Gi', '512Ki', '100M', '1048576'."
        )

    num_part, suffix_part = match.groups()
    num = float(num_part)
    suffix = (suffix_part or "").strip()

    if num < 0:
        raise ValueError(f"Memory quantity cannot be negative: '{quantity}'")

    if not suffix:
        # Plain bytes
        total_bytes = int(round(num))
    else:
        suffix_lower = suffix.lower()
        if suffix_lower in MEMORY_BINARY_MULTIPLIERS:
            multiplier = MEMORY_BINARY_MULTIPLIERS[suffix_lower]
            total_bytes = int(round(num * multiplier))
        elif suffix_lower in MEMORY_DECIMAL_MULTIPLIERS:
            multiplier = MEMORY_DECIMAL_MULTIPLIERS[suffix_lower]
            total_bytes = int(round(num * multiplier))
        else:
            raise ValueError(
                f"Unknown memory unit suffix '{suffix}' in '{quantity}'. "
                f"Supported binary units: Ki, Mi, Gi, Ti, Pi, Ei. "
                f"Supported decimal units: K, M, G, T, P, E."
            )

    if total_bytes > 10**18:
        raise ValueError(f"Memory quantity exceeds maximum cluster bound (1 Exabyte): '{quantity}'")

    # Calculate standard representations
    kib = round(total_bytes / 1024, 2)
    mib = round(total_bytes / (1024**2), 2)
    gib = round(total_bytes / (1024**3), 3)
    tib = round(total_bytes / (1024**4), 4)

    kb = round(total_bytes / 1000, 2)
    mb = round(total_bytes / 1_000_000, 2)
    gb = round(total_bytes / 1_000_000_000, 3)

    representations = {
        "bytes": total_bytes,
        "formatted_bytes": f"{total_bytes:,} bytes",
        "binary_si": {
            "Ki": f"{int(kib) if kib.is_integer() else kib}Ki",
            "Mi": f"{int(mib) if mib.is_integer() else mib}Mi",
            "Gi": f"{int(gib) if gib.is_integer() else gib}Gi",
            "Ti": f"{int(tib) if tib.is_integer() else tib}Ti",
        },
        "decimal_si": {
            "K": f"{int(kb) if kb.is_integer() else kb}K",
            "M": f"{int(mb) if mb.is_integer() else mb}M",
            "G": f"{int(gb) if gb.is_integer() else gb}G",
        },
    }

    target_converted = None
    if target_unit:
        tu = target_unit.strip().lower()
        if tu in ("b", "byte", "bytes"):
            target_converted = f"{total_bytes:,} bytes"
        elif tu in ("ki", "kib"):
            target_converted = f"{kib} Ki"
        elif tu in ("mi", "mib"):
            target_converted = f"{mib} Mi"
        elif tu in ("gi", "gib"):
            target_converted = f"{gib} Gi"
        elif tu in ("ti", "tib"):
            target_converted = f"{tib} Ti"
        elif tu in ("k", "kb"):
            target_converted = f"{kb} K"
        elif tu in ("m", "mb"):
            target_converted = f"{mb} M"
        elif tu in ("g", "gb"):
            target_converted = f"{gb} G"
        else:
            target_converted = f"{mib} Mi"

    explanation = (
        f"{quantity} Memory is equivalent to {total_bytes:,} bytes ({mib} Mi or {gib} Gi). "
        f"Kubernetes binary SI units (Ki, Mi, Gi) use base-2 (1024-based) multipliers, "
        f"whereas decimal units (K, M, G) use base-10 (1000-based) multipliers."
    )

    return {
        "tool": "k8s_quantity_converter",
        "input": quantity,
        "resource_type": "memory",
        "canonical_value": f"{total_bytes:,} bytes",
        "representations": representations,
        "target_conversion": target_converted,
        "explanation": explanation,
        "success": True,
    }


def k8s_quantity_converter(quantity: str, target_unit: Optional[str] = None) -> Dict[str, Any]:
    """Convert Kubernetes CPU or Memory quantity into standard canonical representations.

    Args:
        quantity: A Kubernetes resource quantity string (e.g. '500m', '2', '128Mi', '2Gi').
        target_unit: Optional target unit representation ('cores', 'm', 'Mi', 'Gi', 'bytes').

    Returns:
        Structured dictionary containing parsed type, canonical value, representations, and explanation.
    """
    if not quantity or not isinstance(quantity, str) or not quantity.strip():
        return {
            "tool": "k8s_quantity_converter",
            "input": quantity,
            "error": "Quantity parameter must be a non-empty string.",
            "success": False,
        }

    q = quantity.strip()
    logger.info("Executing k8s_quantity_converter for '%s' (target_unit=%s)", q, target_unit)

    # Determine whether CPU or Memory:
    # CPU indicators: ends with 'm' (millicores) or explicitly specifies cores / cpu
    # Memory indicators: contains Ki, Mi, Gi, Ti, Pi, Ei, or decimal K, M, G (or ends in b/bytes)
    is_cpu = False
    lower = q.lower()

    if re.search(r"\b(cpu|cores?|millicores?)\b", lower):
        is_cpu = True
    elif re.search(r"^[0-9]+(?:\.[0-9]+)?\s*m$", q):
        # Kubernetes CPU millicores are strictly lowercase 'm' (e.g. 500m)
        is_cpu = True
    elif target_unit and target_unit.lower() in ("cores", "core", "c", "m", "millicores"):
        is_cpu = True
    elif re.search(r"(ki|mi|gi|ti|pi|ei|kb|mb|gb|bytes)", lower) or q.endswith(("M", "G", "T", "P", "E", "K")):
        # Kubernetes decimal memory suffixes are uppercase (e.g. 100M = 100 Megabytes)
        is_cpu = False
    elif q.endswith("m") and not lower.endswith("mi"):
        is_cpu = True
    elif re.match(r"^[0-9]+(?:\.[0-9]+)?$", q):
        # Plain number: if <= 128, typically CPU cores; if larger, bytes
        val = float(q)
        if val <= 64:
            is_cpu = True
        else:
            is_cpu = False

    try:
        if is_cpu:
            return _parse_cpu_quantity(q, target_unit)
        else:
            return _parse_memory_quantity(q, target_unit)
    except Exception as exc:
        logger.warning("k8s_quantity_converter failed for '%s': %s", q, exc)
        return {
            "tool": "k8s_quantity_converter",
            "input": quantity,
            "error": str(exc),
            "success": False,
        }


# ---------------------------------------------------------------------------
# Tool 2: k8s_rag_search (Official Documentation Retrieval & Grounding)
# ---------------------------------------------------------------------------

def k8s_rag_search(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Retrieve official Kubernetes documentation and synthesize an authoritative answer.

    Args:
        query: User's Kubernetes conceptual or command question.
        top_k: Number of relevant documentation chunks to retrieve (default: 3).

    Returns:
        Structured dictionary containing answer, citations, confidence, and context sufficiency.
    """
    if not query or not isinstance(query, str) or not query.strip():
        return {
            "tool": "k8s_rag_search",
            "query": query,
            "error": "Query parameter must be a non-empty string.",
            "success": False,
        }

    try:
        k = int(top_k)
        if k < 1 or k > 10:
            k = 3
    except (ValueError, TypeError):
        k = 3

    logger.info("Executing k8s_rag_search for '%s' (top_k=%d)", query.strip(), k)
    try:
        rag_output = execute_rag_pipeline(question=query.strip(), top_k=k)
        rag_dict = rag_output.to_dict() if hasattr(rag_output, "to_dict") else dict(rag_output)
        return {
            "tool": "k8s_rag_search",
            "query": query.strip(),
            "answer": rag_dict.get("answer", ""),
            "citations": rag_dict.get("citations", []),
            "confidence": rag_dict.get("confidence", "low"),
            "context_sufficient": rag_dict.get("context_sufficient", False),
            "sources_count": len(rag_dict.get("citations", [])),
            "retrieval_method": "vector_semantic",
            "success": True,
        }
    except Exception as exc:
        logger.error("k8s_rag_search failed for query '%s': %s", query, exc)
        return {
            "tool": "k8s_rag_search",
            "query": query,
            "error": str(exc),
            "success": False,
        }


# ---------------------------------------------------------------------------
# Tool Schemas & Registry (OpenAI / LangChain Compatible)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "k8s_rag_search",
        "description": (
            "Retrieve official Kubernetes documentation and generate an authoritative, "
            "citation-backed answer for conceptual questions, kubectl commands, and cluster architecture."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The Kubernetes concept, kubectl command, or question to research.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of documentation chunks to retrieve (default: 3, max: 10).",
                    "default": 3,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "k8s_quantity_converter",
        "description": (
            "Convert Kubernetes resource quantities (CPU millicores/cores, Memory bytes/Ki/Mi/Gi/Ti/K/M/G) "
            "into standard canonical units and human-readable formats. "
            "Note: In production workflows, this tool requires human approval before execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quantity": {
                    "type": "string",
                    "description": "The Kubernetes resource quantity string (e.g., '500m', '2', '128Mi', '2Gi', '100M').",
                },
                "target_unit": {
                    "type": "string",
                    "description": "Optional desired unit to convert into (e.g., 'cores', 'm', 'Mi', 'Gi', 'bytes').",
                },
            },
            "required": ["quantity"],
        },
    },
]

TOOL_REGISTRY = {
    "k8s_rag_search": k8s_rag_search,
    "k8s_quantity_converter": k8s_quantity_converter,
}


def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """Retrieve schema definition for a registered tool."""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema
    return None


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Safely dispatch and execute a tool by name with strict validation.

    Args:
        name: The registered tool name.
        arguments: Dictionary of arguments matching the tool's schema.

    Returns:
        Structured tool execution dictionary with success flag.
    """
    if not isinstance(name, str) or not name.strip():
        return {
            "tool": str(name),
            "error": "Tool name must be a non-empty string.",
            "success": False,
        }

    tool_name = name.strip()
    if tool_name not in TOOL_REGISTRY:
        return {
            "tool": tool_name,
            "error": f"Tool '{tool_name}' not found. Available tools: {list(TOOL_REGISTRY.keys())}",
            "success": False,
        }

    if not isinstance(arguments, dict):
        return {
            "tool": tool_name,
            "error": f"Tool arguments must be a dictionary, received {type(arguments).__name__}.",
            "success": False,
        }

    func = TOOL_REGISTRY[tool_name]
    schema = get_tool_schema(tool_name)

    # Validate required arguments
    if schema and "parameters" in schema:
        required_keys = schema["parameters"].get("required", [])
        missing = [k for k in required_keys if k not in arguments or arguments[k] is None]
        if missing:
            return {
                "tool": tool_name,
                "error": f"Missing required arguments for tool '{tool_name}': {missing}",
                "success": False,
            }

    try:
        return func(**arguments)
    except TypeError as te:
        logger.warning("Argument mismatch executing '%s' with %s: %s", tool_name, arguments, te)
        return {
            "tool": tool_name,
            "error": f"Invalid arguments for tool '{tool_name}': {te}",
            "success": False,
        }
    except Exception as exc:
        logger.error("Execution error in tool '%s': %s", tool_name, exc)
        return {
            "tool": tool_name,
            "error": f"Error executing tool '{tool_name}': {exc}",
            "success": False,
        }
