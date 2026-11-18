"""
app/tools.py - Production-Quality KubeCoach Agent Tools & Registry (Day 9)

Implements two deterministic, safe, read-only tools for the KubeCoach AI Agent:
1. `k8s_rag_search`: Retrieval-Augmented Generation over official Kubernetes docs
   preserving title, URL, page, and chunk metadata, with honest insufficient-context reporting.
2. `k8s_quantity_converter`: Project-card assigned developer tool (SJ-58) using exact
   `decimal.Decimal` arithmetic to parse, convert, and compare Kubernetes CPU and Memory
   resource quantities (distinguishing binary SI vs. decimal SI suffixes).
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.rag import execute_rag_pipeline

logger = logging.getLogger("kubecoach.tools")

# ---------------------------------------------------------------------------
# Constants & Exact Decimal Multipliers (Official Kubernetes Quantity Spec)
# https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/
# ---------------------------------------------------------------------------

BINARY_SI_MULTIPLIERS: Dict[str, Decimal] = {
    "Ki": Decimal(1024),
    "Mi": Decimal(1024**2),
    "Gi": Decimal(1024**3),
    "Ti": Decimal(1024**4),
    "Pi": Decimal(1024**5),
    "Ei": Decimal(1024**6),
}

DECIMAL_SI_MULTIPLIERS: Dict[str, Decimal] = {
    "k": Decimal(1000),
    "K": Decimal(1000),
    "M": Decimal(1000**2),
    "G": Decimal(1000**3),
    "T": Decimal(1000**4),
    "P": Decimal(1000**5),
    "E": Decimal(1000**6),
}

MAX_CPU_CORES = Decimal("10000000")
MAX_MEMORY_BYTES = Decimal("1000000000000000000")  # 10^18 bytes (1 Exabyte)

SUPPORTED_CPU_TARGET_UNITS = {"m", "millicore", "millicores", "core", "cores", "c"}
SUPPORTED_MEMORY_TARGET_UNITS = {
    "b", "byte", "bytes",
    "ki", "kib", "mi", "mib", "gi", "gib", "ti", "tib", "pi", "pib", "ei", "eib",
    "k", "kb", "m", "mb", "g", "gb", "t", "tb", "p", "pb", "e", "eb",
}


def _format_decimal(value: Decimal, max_places: int = 6) -> str:
    """Format a Decimal cleanly without scientific notation or redundant trailing zeros."""
    quantizer = Decimal(10) ** (-max_places)
    rounded = value.quantize(quantizer, rounding=ROUND_HALF_UP)
    normalized = format(rounded, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized or "0"


def _to_number(value: Decimal, max_places: int = 6) -> Any:
    """Convert Decimal to int if exact integer, else rounded float for JSON serialization."""
    formatted = _format_decimal(value, max_places=max_places)
    return int(formatted) if "." not in formatted else float(formatted)


def _classify_and_parse_quantity(
    raw_quantity: str,
    hint_type: Optional[str] = None,
) -> Tuple[str, Decimal, str]:
    """Parse a Kubernetes quantity string into (resource_type, canonical_decimal, suffix_system).

    Canonical units:
        - CPU: cores (Decimal)
        - Memory: bytes (Decimal)

    Raises:
        ValueError: On missing, negative, malformed, unsupported suffix, or out-of-bounds values.
    """
    if not isinstance(raw_quantity, str) or not raw_quantity.strip():
        raise ValueError("Quantity must be a non-empty string.")

    text = raw_quantity.strip()

    # Explicitly reject negative values immediately with clear message
    if text.startswith("-"):
        raise ValueError(f"Kubernetes resource quantities cannot be negative: '{raw_quantity}'.")

    # Reject NaN / Infinity
    if text.lower() in ("nan", "inf", "+inf", "-inf", "infinity"):
        raise ValueError(f"Invalid non-finite Kubernetes quantity: '{raw_quantity}'.")

    # Normalize optional descriptive words like '2 cores' or '500 millicores' or '1024 bytes'
    explicit_cpu_match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(cores?|cpu|millicores?)$", text, re.IGNORECASE)
    if explicit_cpu_match:
        num_str, unit_word = explicit_cpu_match.groups()
        val = Decimal(num_str)
        if unit_word.lower().startswith("milli"):
            cores = val / Decimal("1000")
            if cores > MAX_CPU_CORES:
                raise ValueError(f"CPU quantity exceeds cluster limit ({MAX_CPU_CORES} cores): '{raw_quantity}'.")
            return ("cpu", cores, "millicores")
        if val > MAX_CPU_CORES:
            raise ValueError(f"CPU quantity exceeds cluster limit ({MAX_CPU_CORES} cores): '{raw_quantity}'.")
        return ("cpu", val, "cores")

    explicit_bytes_match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(bytes?|B)$", text)
    if explicit_bytes_match:
        num_str = explicit_bytes_match.group(1)
        val = Decimal(num_str)
        if val > MAX_MEMORY_BYTES:
            raise ValueError(f"Memory quantity exceeds cluster limit (1 Exabyte): '{raw_quantity}'.")
        return ("memory", val, "bytes")

    # Strict Kubernetes quantity token pattern: <number><optional_suffix>
    token_match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?$", text)
    if not token_match:
        raise ValueError(
            f"Invalid Kubernetes quantity format: '{raw_quantity}'. "
            "Use examples like '500m', '1000m', '2' (CPU) or '512Mi', '1Gi', '1G' (Memory)."
        )

    num_str, suffix = token_match.groups()
    try:
        num = Decimal(num_str)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid numeric value in quantity '{raw_quantity}'.") from exc

    if num < 0:
        raise ValueError(f"Kubernetes resource quantities cannot be negative: '{raw_quantity}'.")

    # Case 1: Plain number with no suffix
    if not suffix:
        if hint_type == "memory" or (hint_type != "cpu" and num > Decimal("64")):
            if num > MAX_MEMORY_BYTES:
                raise ValueError(f"Memory quantity exceeds cluster limit (1 Exabyte): '{raw_quantity}'.")
            return ("memory", num, "bytes")
        if num > MAX_CPU_CORES:
            raise ValueError(f"CPU quantity exceeds cluster limit ({MAX_CPU_CORES} cores): '{raw_quantity}'.")
        return ("cpu", num, "cores")

    # Case 2: Exact lowercase 'm' -> Kubernetes CPU millicores
    if suffix == "m":
        cores = num / Decimal("1000")
        if cores > MAX_CPU_CORES:
            raise ValueError(f"CPU quantity exceeds cluster limit ({MAX_CPU_CORES} cores): '{raw_quantity}'.")
        return ("cpu", cores, "millicores")

    # Case 3: Exact Binary SI memory suffixes (Ki, Mi, Gi, Ti, Pi, Ei)
    if suffix in BINARY_SI_MULTIPLIERS:
        total_bytes = num * BINARY_SI_MULTIPLIERS[suffix]
        if total_bytes > MAX_MEMORY_BYTES:
            raise ValueError(f"Memory quantity exceeds cluster limit (1 Exabyte): '{raw_quantity}'.")
        return ("memory", total_bytes, "binary_si")

    # Case 4: Exact Decimal SI memory suffixes (k, K, M, G, T, P, E)
    if suffix in DECIMAL_SI_MULTIPLIERS:
        total_bytes = num * DECIMAL_SI_MULTIPLIERS[suffix]
        if total_bytes > MAX_MEMORY_BYTES:
            raise ValueError(f"Memory quantity exceeds cluster limit (1 Exabyte): '{raw_quantity}'.")
        return ("memory", total_bytes, "decimal_si")

    # Case 5: Unsupported suffix -> reject explicitly
    raise ValueError(
        f"Unsupported Kubernetes quantity suffix '{suffix}' in '{raw_quantity}'. "
        "Supported CPU suffixes: 'm' (millicores) or plain cores. "
        "Supported Memory binary SI suffixes: Ki, Mi, Gi, Ti, Pi, Ei (base 1024). "
        "Supported Memory decimal SI suffixes: k, M, G, T, P, E (base 1000)."
    )


def _build_cpu_payload(
    raw_quantity: str,
    cores: Decimal,
    suffix_system: str,
    target_unit: Optional[str] = None,
) -> Dict[str, Any]:
    """Build structured conversion dictionary for a parsed CPU quantity."""
    millicores = cores * Decimal("1000")
    cores_str = _format_decimal(cores, max_places=6)
    milli_str = _format_decimal(millicores, max_places=3)

    representations = {
        "cores": _to_number(cores, max_places=6),
        "cores_exact": cores_str,
        "millicores": f"{milli_str}m",
        "millicores_numeric": _to_number(millicores, max_places=3),
    }

    target_conversion = None
    if target_unit:
        tu = target_unit.strip().lower()
        if tu in ("m", "millicore", "millicores"):
            target_conversion = f"{milli_str}m"
        elif tu in ("c", "core", "cores"):
            unit_label = "core" if cores == Decimal("1") else "cores"
            target_conversion = f"{cores_str} {unit_label}"
        else:
            raise ValueError(
                f"Unsupported target_unit '{target_unit}' for CPU quantity. "
                "Supported CPU target units: 'cores', 'm'."
            )

    core_word = "core" if cores == Decimal("1") else "cores"
    explanation = (
        f"{raw_quantity} CPU equals {cores_str} {core_word} ({milli_str}m / {milli_str} millicores). "
        "In Kubernetes, 1 CPU core is strictly equal to 1000m (1000 millicores)."
    )

    return {
        "tool": "k8s_quantity_converter",
        "input": raw_quantity,
        "resource_type": "cpu",
        "unit_system": suffix_system,
        "canonical_value": f"{cores_str} {core_word}",
        "canonical_numeric": _to_number(cores, max_places=6),
        "representations": representations,
        "target_conversion": target_conversion,
        "explanation": explanation,
        "success": True,
    }


def _build_memory_payload(
    raw_quantity: str,
    total_bytes: Decimal,
    suffix_system: str,
    target_unit: Optional[str] = None,
) -> Dict[str, Any]:
    """Build structured conversion dictionary for a parsed Memory quantity."""
    bytes_int = int(total_bytes.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    kib = total_bytes / BINARY_SI_MULTIPLIERS["Ki"]
    mib = total_bytes / BINARY_SI_MULTIPLIERS["Mi"]
    gib = total_bytes / BINARY_SI_MULTIPLIERS["Gi"]
    tib = total_bytes / BINARY_SI_MULTIPLIERS["Ti"]

    kb = total_bytes / DECIMAL_SI_MULTIPLIERS["k"]
    mb = total_bytes / DECIMAL_SI_MULTIPLIERS["M"]
    gb = total_bytes / DECIMAL_SI_MULTIPLIERS["G"]
    tb = total_bytes / DECIMAL_SI_MULTIPLIERS["T"]

    representations = {
        "bytes": bytes_int,
        "formatted_bytes": f"{bytes_int:,} bytes",
        "binary_si": {
            "Ki": f"{_format_decimal(kib, 4)}Ki",
            "Mi": f"{_format_decimal(mib, 4)}Mi",
            "Gi": f"{_format_decimal(gib, 6)}Gi",
            "Ti": f"{_format_decimal(tib, 6)}Ti",
            "Mi_numeric": _to_number(mib, 4),
            "Gi_numeric": _to_number(gib, 6),
        },
        "decimal_si": {
            "k": f"{_format_decimal(kb, 4)}k",
            "M": f"{_format_decimal(mb, 4)}M",
            "G": f"{_format_decimal(gb, 6)}G",
            "T": f"{_format_decimal(tb, 6)}T",
            "M_numeric": _to_number(mb, 4),
            "G_numeric": _to_number(gb, 6),
        },
    }

    target_conversion = None
    if target_unit:
        tu = target_unit.strip()
        tu_lower = tu.lower()
        if tu_lower in ("b", "byte", "bytes"):
            target_conversion = f"{bytes_int:,} bytes"
        elif tu_lower in ("ki", "kib"):
            target_conversion = f"{_format_decimal(kib, 4)} Ki"
        elif tu_lower in ("mi", "mib"):
            target_conversion = f"{_format_decimal(mib, 4)} Mi"
        elif tu_lower in ("gi", "gib"):
            target_conversion = f"{_format_decimal(gib, 6)} Gi"
        elif tu_lower in ("ti", "tib"):
            target_conversion = f"{_format_decimal(tib, 6)} Ti"
        elif tu_lower in ("k", "kb"):
            target_conversion = f"{_format_decimal(kb, 4)} k"
        elif tu_lower in ("m", "mb"):
            target_conversion = f"{_format_decimal(mb, 4)} M"
        elif tu_lower in ("g", "gb"):
            target_conversion = f"{_format_decimal(gb, 6)} G"
        elif tu_lower in ("t", "tb"):
            target_conversion = f"{_format_decimal(tb, 6)} T"
        else:
            raise ValueError(
                f"Unsupported target_unit '{target_unit}' for Memory quantity. "
                "Supported Memory target units: bytes, Ki, Mi, Gi, Ti, k, M, G, T."
            )

    mib_str = _format_decimal(mib, 4)
    gib_str = _format_decimal(gib, 6)
    gb_str = _format_decimal(gb, 6)
    system_note = (
        "binary SI (base 1024: 1Gi = 1024Mi = 1,073,741,824 bytes)"
        if suffix_system == "binary_si"
        else "decimal SI (base 1000: 1G = 1,000,000,000 bytes)"
        if suffix_system == "decimal_si"
        else "raw bytes"
    )
    explanation = (
        f"{raw_quantity} Memory ({system_note}) equals {bytes_int:,} bytes "
        f"({mib_str} Mi / {gib_str} Gi binary, or {gb_str} G decimal)."
    )

    return {
        "tool": "k8s_quantity_converter",
        "input": raw_quantity,
        "resource_type": "memory",
        "unit_system": suffix_system,
        "canonical_value": f"{bytes_int:,} bytes",
        "canonical_numeric": bytes_int,
        "representations": representations,
        "target_conversion": target_conversion,
        "explanation": explanation,
        "success": True,
    }


def compare_k8s_quantities(quantity_a: str, quantity_b: str) -> Dict[str, Any]:
    """Deterministically compare two Kubernetes quantities using exact Decimal arithmetic."""
    type_a, val_a, sys_a = _classify_and_parse_quantity(quantity_a)
    type_b, val_b, sys_b = _classify_and_parse_quantity(quantity_b, hint_type=type_a)

    if type_a != type_b:
        raise ValueError(
            f"Cannot compare incompatible resource types: '{quantity_a}' ({type_a}) vs. "
            f"'{quantity_b}' ({type_b}). Both quantities must be CPU or both Memory."
        )

    diff = val_a - val_b
    if diff > 0:
        relation = "greater_than"
        symbol = ">"
    elif diff < 0:
        relation = "less_than"
        symbol = "<"
    else:
        relation = "equal"
        symbol = "=="

    ratio = _to_number(val_a / val_b, max_places=6) if val_b != 0 else None

    if type_a == "cpu":
        diff_milli = diff * Decimal("1000")
        summary = (
            f"{quantity_a} ({_format_decimal(val_a)} cores) is {relation.replace('_', ' ')} "
            f"{quantity_b} ({_format_decimal(val_b)} cores) [{quantity_a} {symbol} {quantity_b}]. "
            f"Difference: {_format_decimal(abs(diff))} cores ({_format_decimal(abs(diff_milli), 3)}m)."
        )
        return {
            "quantity_a": quantity_a,
            "quantity_b": quantity_b,
            "resource_type": "cpu",
            "relation": relation,
            "symbol": symbol,
            "value_a_cores": _to_number(val_a),
            "value_b_cores": _to_number(val_b),
            "difference_cores": _to_number(diff),
            "difference_millicores": _to_number(diff_milli, 3),
            "ratio": ratio,
            "summary": summary,
        }

    # Memory comparison
    bytes_a = int(val_a.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    bytes_b = int(val_b.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    diff_bytes = bytes_a - bytes_b
    diff_mib = abs(diff) / BINARY_SI_MULTIPLIERS["Mi"]

    summary = (
        f"{quantity_a} ({bytes_a:,} bytes, {sys_a}) is {relation.replace('_', ' ')} "
        f"{quantity_b} ({bytes_b:,} bytes, {sys_b}) [{quantity_a} {symbol} {quantity_b}]. "
        f"Difference: {abs(diff_bytes):,} bytes ({_format_decimal(diff_mib, 4)} Mi)."
    )
    return {
        "quantity_a": quantity_a,
        "quantity_b": quantity_b,
        "resource_type": "memory",
        "relation": relation,
        "symbol": symbol,
        "value_a_bytes": bytes_a,
        "value_b_bytes": bytes_b,
        "difference_bytes": diff_bytes,
        "difference_mib": _to_number(diff_mib, 4),
        "ratio": ratio,
        "summary": summary,
    }


def k8s_quantity_converter(
    quantity: str,
    target_unit: Optional[str] = None,
    compare_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert and optionally compare Kubernetes CPU or Memory quantities deterministically.

    Uses exact `decimal.Decimal` arithmetic with strict distinction between binary SI
    (Ki/Mi/Gi/Ti, base 1024) and decimal SI (k/M/G/T, base 1000) suffixes.

    Args:
        quantity: Primary Kubernetes resource quantity (e.g., '500m', '1000m', '2', '512Mi', '1Gi', '1G').
        target_unit: Optional desired output unit (e.g., 'cores', 'm', 'Mi', 'Gi', 'bytes', 'G').
        compare_to: Optional second Kubernetes quantity to compare against (e.g., '1G', '1').

    Returns:
        Structured dictionary with canonical values, unit conversions, optional comparison,
        explanation, and boolean success flag.
    """
    if not isinstance(quantity, str) or not quantity.strip():
        return {
            "tool": "k8s_quantity_converter",
            "input": quantity,
            "error": "Quantity parameter must be a non-empty string.",
            "success": False,
        }

    q = quantity.strip()
    logger.info(
        "Executing k8s_quantity_converter: quantity='%s', target_unit=%s, compare_to=%s",
        q,
        target_unit,
        compare_to,
    )

    # Infer type hint if target_unit clearly indicates CPU or Memory
    hint_type: Optional[str] = None
    if target_unit:
        tu_lower = target_unit.strip().lower()
        if tu_lower in ("core", "cores", "c", "millicore", "millicores"):
            hint_type = "cpu"
        elif tu_lower in ("b", "byte", "bytes", "ki", "kib", "mi", "mib", "gi", "gib", "ti", "tib", "kb", "mb", "gb"):
            hint_type = "memory"

    try:
        resource_type, canonical_val, suffix_system = _classify_and_parse_quantity(q, hint_type=hint_type)

        if resource_type == "cpu":
            payload = _build_cpu_payload(q, canonical_val, suffix_system, target_unit=target_unit)
        else:
            payload = _build_memory_payload(q, canonical_val, suffix_system, target_unit=target_unit)

        if compare_to is not None and str(compare_to).strip():
            comparison = compare_k8s_quantities(q, str(compare_to).strip())
            payload["comparison"] = comparison
            payload["explanation"] = f"{payload['explanation']} {comparison['summary']}"

        return payload
    except Exception as exc:
        logger.warning("k8s_quantity_converter validation/conversion error for '%s': %s", q, exc)
        return {
            "tool": "k8s_quantity_converter",
            "input": quantity,
            "error": str(exc),
            "success": False,
        }


# ---------------------------------------------------------------------------
# Tool A: k8s_rag_search (Official Documentation Retrieval & Grounding)
# ---------------------------------------------------------------------------

def k8s_rag_search(query: str, top_k: int = 3) -> Dict[str, Any]:
    """Search the Kubernetes knowledge base via the existing Day 8 RAG pipeline.

    Preserves document title, source URL, page, and chunk metadata, and explicitly
    reports insufficient context when the documentation cannot answer the question.

    Args:
        query: Natural-language Kubernetes concept or kubectl command question.
        top_k: Number of chunks to retrieve from ChromaDB (1 to 10, default 3).

    Returns:
        Structured dictionary with answer, citations, confidence, and context_sufficient.
    """
    if not isinstance(query, str) or not query.strip():
        return {
            "tool": "k8s_rag_search",
            "query": query,
            "error": "Query parameter must be a non-empty string.",
            "citations": [],
            "context_sufficient": False,
            "success": False,
        }

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        try:
            top_k = int(top_k)
        except (ValueError, TypeError):
            return {
                "tool": "k8s_rag_search",
                "query": query.strip(),
                "error": "top_k must be an integer between 1 and 10.",
                "citations": [],
                "context_sufficient": False,
                "success": False,
            }

    if top_k < 1 or top_k > 10:
        return {
            "tool": "k8s_rag_search",
            "query": query.strip(),
            "error": f"top_k must be between 1 and 10 (received {top_k}).",
            "citations": [],
            "context_sufficient": False,
            "success": False,
        }

    clean_query = query.strip()
    logger.info("Executing k8s_rag_search: query='%s', top_k=%d", clean_query, top_k)

    try:
        rag_result = execute_rag_pipeline(question=clean_query, top_k=top_k)
        rag_dict = rag_result.to_dict() if hasattr(rag_result, "to_dict") else dict(rag_result)
        context_sufficient = bool(rag_dict.get("context_sufficient", False))
        citations = rag_dict.get("citations", []) if context_sufficient else []

        return {
            "tool": "k8s_rag_search",
            "query": clean_query,
            "answer": rag_dict.get("answer", ""),
            "citations": citations,
            "confidence": rag_dict.get("confidence", "low"),
            "context_sufficient": context_sufficient,
            "sources_count": len(citations),
            "retrieval_method": "vector_semantic",
            "success": True,
        }
    except Exception as exc:
        logger.error("k8s_rag_search execution error for '%s': %s", clean_query, exc)
        return {
            "tool": "k8s_rag_search",
            "query": clean_query,
            "error": f"RAG search failed: {exc}",
            "citations": [],
            "context_sufficient": False,
            "success": False,
        }


# ---------------------------------------------------------------------------
# Tool Schemas, Registry, Argument Validation & Safe Dispatcher
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "k8s_rag_search",
        "description": (
            "Search the official Kubernetes documentation knowledge base using RAG. "
            "Returns grounded explanations, kubectl commands, and verifiable source citations "
            "(title, URL, page), or an explicit insufficient-context result when unavailable."
        ),
        "requires_approval": False,
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The Kubernetes concept, object, or kubectl command question to search.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of relevant documentation chunks to retrieve (1-10, default: 3).",
                    "default": 3,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "k8s_quantity_converter",
        "description": (
            "Deterministically parse, convert, and compare Kubernetes CPU (m, cores) and Memory "
            "(Ki, Mi, Gi, Ti, Pi, Ei binary SI vs. k, M, G, T, P, E decimal SI) resource quantities "
            "using exact Decimal arithmetic. Requires human approval in LangGraph workflows."
        ),
        "requires_approval": True,
        "parameters": {
            "type": "object",
            "properties": {
                "quantity": {
                    "type": "string",
                    "description": "Primary Kubernetes quantity string (e.g., '500m', '2', '512Mi', '1Gi', '1G').",
                },
                "target_unit": {
                    "type": "string",
                    "description": "Optional output unit (e.g., 'cores', 'm', 'Mi', 'Gi', 'bytes', 'G').",
                },
                "compare_to": {
                    "type": "string",
                    "description": "Optional second Kubernetes quantity to compare against (e.g., '1', '1G', '1Gi').",
                },
            },
            "required": ["quantity"],
            "additionalProperties": False,
        },
    },
]

TOOL_REGISTRY: Dict[str, Callable[..., Dict[str, Any]]] = {
    "k8s_rag_search": k8s_rag_search,
    "k8s_quantity_converter": k8s_quantity_converter,
}


def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """Return the JSON schema descriptor for a registered tool, or None if unregistered."""
    for schema in TOOL_SCHEMAS:
        if schema["name"] == name:
            return schema
    return None


def validate_tool_call(name: str, arguments: Any) -> Tuple[bool, Optional[str]]:
    """Validate that a tool is registered and its arguments conform to its schema.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not isinstance(name, str) or not name.strip():
        return (False, "Tool name must be a non-empty string.")

    tool_name = name.strip()
    if tool_name not in TOOL_REGISTRY:
        return (
            False,
            f"Tool '{tool_name}' is not registered. Available tools: {list(TOOL_REGISTRY.keys())}",
        )

    if not isinstance(arguments, dict):
        return (
            False,
            f"Tool arguments must be a dictionary, received {type(arguments).__name__}.",
        )

    schema = get_tool_schema(tool_name)
    if not schema:
        return (False, f"Schema definition missing for tool '{tool_name}'.")

    params_schema = schema.get("parameters", {})
    allowed_props = params_schema.get("properties", {})
    required_keys = params_schema.get("required", [])

    # Check unknown arguments
    unknown_keys = [k for k in arguments.keys() if k not in allowed_props]
    if unknown_keys:
        return (
            False,
            f"Unexpected argument(s) for tool '{tool_name}': {unknown_keys}. "
            f"Allowed arguments: {list(allowed_props.keys())}",
        )

    # Check required arguments
    missing_keys = [
        k for k in required_keys
        if k not in arguments or arguments[k] is None or (isinstance(arguments[k], str) and not arguments[k].strip())
    ]
    if missing_keys:
        return (
            False,
            f"Missing required argument(s) for tool '{tool_name}': {missing_keys}.",
        )

    # Basic type validation against schema
    for key, val in arguments.items():
        if val is None:
            continue
        expected_type = allowed_props[key].get("type")
        if expected_type == "string" and not isinstance(val, str):
            return (
                False,
                f"Argument '{key}' for tool '{tool_name}' must be a string, got {type(val).__name__}.",
            )
        if expected_type == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
            return (
                False,
                f"Argument '{key}' for tool '{tool_name}' must be an integer, got {type(val).__name__}.",
            )

    return (True, None)


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Safely validate and execute a registered read-only tool.

    Args:
        name: Registered tool name.
        arguments: Dictionary of arguments matching the tool schema.

    Returns:
        Structured dictionary with execution output and boolean `success` key.
    """
    is_valid, error_msg = validate_tool_call(name, arguments)
    if not is_valid:
        logger.warning("Tool call validation failed for '%s': %s", name, error_msg)
        return {
            "tool": str(name),
            "error": error_msg,
            "success": False,
        }

    tool_name = name.strip()
    func = TOOL_REGISTRY[tool_name]
    try:
        return func(**arguments)
    except Exception as exc:
        logger.error("Unexpected execution error in tool '%s': %s", tool_name, exc)
        return {
            "tool": tool_name,
            "error": f"Tool execution failed for '{tool_name}': {exc}",
            "success": False,
        }
