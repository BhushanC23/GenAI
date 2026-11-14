"""LLM Provider wrapper module for KubeCoach.

Supports Groq, Google Gemini, and a grounded Mock provider for local/offline testing.
Reads API credentials from .env via python-dotenv, isolates provider-specific logic,
enforces structured JSON output (answer, confidence, follow_up), and provides
comprehensive error handling for timeouts, rate limits (429), and authentication.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from app.records import load_records
from app.smart_search import smart_search

# Load environment variables from .env file if present
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kubecoach.llm")

# Default Configurations
DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
DEFAULT_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
DEFAULT_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "25.0"))


# Custom Exceptions
class LLMError(Exception):
    """Base exception for all LLM provider errors."""


class LLMTimeoutError(LLMError):
    """Raised when an LLM provider request times out."""


class LLMRateLimitError(LLMError):
    """Raised when an LLM provider rate limit (HTTP 429) is exceeded."""


class LLMAuthenticationError(LLMError):
    """Raised when an API key is missing, unauthorized, or invalid."""


class LLMResponseParsingError(LLMError):
    """Raised when the provider output cannot be parsed into structured JSON."""


def load_system_prompt(path: Optional[Path] = None) -> str:
    """Read the master system prompt from prompts/system_prompt.md."""
    target = path or (BASE_DIR / "prompts" / "system_prompt.md")
    if target.is_file():
        return target.read_text(encoding="utf-8").strip()
    return (
        "You are KubeCoach, a Kubernetes learning assistant. Explain concepts in beginner-friendly "
        "English with kubectl commands. Return JSON with 'answer', 'confidence', and 'follow_up'."
    )


def extract_structured_json(raw_text: str) -> Dict[str, str]:
    """Parse and clean raw LLM output into required structured JSON.

    Handles markdown code fences (```json ... ```) and text cleanup.
    """
    cleaned = raw_text.strip()
    # Strip markdown code blocks if present
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(1).strip()
    elif cleaned.startswith("{") and cleaned.endswith("}"):
        pass
    else:
        # Attempt to find the first JSON object inside the text
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1].strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, dict):
            raise ValueError("Parsed JSON is not a dictionary.")
    except Exception as exc:
        logger.warning("Could not parse JSON from LLM output: %s. Using fallback parser.", exc)
        return {
            "answer": raw_text.strip(),
            "confidence": "medium",
            "follow_up": "Would you like an example kubectl command for this concept?",
        }

    # Normalize fields
    answer = str(data.get("answer", "")).strip() or raw_text.strip()
    confidence = str(data.get("confidence", "high")).strip().lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    follow_up = str(data.get("follow_up", "")).strip()
    if not follow_up:
        follow_up = "What would you like to explore next about this Kubernetes concept?"

    return {
        "answer": answer,
        "confidence": confidence,
        "follow_up": follow_up,
    }


def call_groq(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Dict[str, str]:
    """Execute inference via Groq's official API."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key.startswith("gsk_your_groq"):
        raise LLMAuthenticationError(
            "GROQ_API_KEY is not configured. Please set a valid key in .env or environment."
        )

    try:
        from groq import (
            APIConnectionError,
            APIError,
            APITimeoutError,
            AuthenticationError,
            Groq,
            RateLimitError,
        )

        client = Groq(api_key=api_key, timeout=timeout)
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        content = completion.choices[0].message.content or ""
        return extract_structured_json(content)
    except AuthenticationError as exc:
        raise LLMAuthenticationError(f"Groq authentication failed: {exc}") from exc
    except RateLimitError as exc:
        raise LLMRateLimitError(f"Groq rate limit exceeded (HTTP 429): {exc}") from exc
    except (APITimeoutError, APIConnectionError) as exc:
        raise LLMTimeoutError(f"Groq request timed out or connection failed: {exc}") from exc
    except APIError as exc:
        raise LLMError(f"Groq API error: {exc}") from exc
    except Exception as exc:
        raise LLMError(f"Unexpected error calling Groq: {exc}") from exc


def call_gemini(
    prompt: str,
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> Dict[str, str]:
    """Execute inference via Google Gemini REST API using httpx."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key.startswith("AIzaSy_your_gemini"):
        raise LLMAuthenticationError(
            "GEMINI_API_KEY is not configured. Please set a valid key in .env or environment."
        )

    endpoint_url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    )

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(endpoint_url, json=payload)

        if resp.status_code == 429:
            raise LLMRateLimitError("Gemini quota or rate limit exceeded (HTTP 429).")
        if resp.status_code in (401, 403):
            raise LLMAuthenticationError(f"Gemini authentication failed: {resp.text}")

        resp.raise_for_status()
        data = resp.json()

        # Extract candidates text
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMError("Gemini returned empty response candidates.")

        content_parts = candidates[0].get("content", {}).get("parts", [])
        raw_text = content_parts[0].get("text", "") if content_parts else ""
        return extract_structured_json(raw_text)

    except httpx.TimeoutException as exc:
        raise LLMTimeoutError(f"Gemini request timed out: {exc}") from exc
    except (LLMAuthenticationError, LLMRateLimitError):
        raise
    except httpx.HTTPStatusError as exc:
        raise LLMError(f"Gemini HTTP error {exc.response.status_code}: {exc.response.text}") from exc
    except Exception as exc:
        raise LLMError(f"Gemini request failed: {exc}") from exc


def call_mock_provider(prompt: str) -> Dict[str, str]:
    """Local, deterministic mock provider grounded in KubeCoach records.

    Used when no API keys are configured, enabling offline development and testing.
    """
    logger.info("Using grounded Mock LLM provider for query: %s", prompt)
    cleaned = prompt.strip()

    # Check for unanswerable topics (e.g. Istio Service Mesh, HashiCorp Nomad)
    if any(k in cleaned.lower() for k in ("istio", "service mesh", "consul", "nomad")):
        return {
            "answer": (
                "Istio and third-party service meshes are not part of core Kubernetes objects covered "
                "in official documentation concepts. In core Kubernetes, Service objects provide stable "
                "L4 networking and Ingress handles L7 routing. To learn Istio, consult the official "
                "istio.io documentation."
            ),
            "confidence": "low",
            "follow_up": "Would you like to know how native Kubernetes Service or Ingress objects work instead?",
        }

    # Query local knowledge base
    records = load_records()
    matches = smart_search(cleaned, records=records, top_k=1)

    if matches and matches[0]["score"] > 0.05:
        match = matches[0]
        return {
            "answer": (
                f"{match['page_title']} ({match['category']}): {match['one_line_definition']} "
                f"Practical command: '{match['key_kubectl_command']}'. "
                f"Default/Limit: {match['limit_or_default']} (Source: {match['source_url']})."
            ),
            "confidence": "high",
            "follow_up": f"Would you like to see how {match['page_title']} relate to other Kubernetes workloads?",
        }

    return {
        "answer": (
            "Kubernetes is an open-source container orchestration platform designed to automate the "
            "deployment, scaling, and management of containerized applications. You can inspect cluster "
            "resources using 'kubectl get pods' or 'kubectl get nodes'."
        ),
        "confidence": "medium",
        "follow_up": "What specific Kubernetes object (Pod, Deployment, Service, ConfigMap) would you like to explore?",
    }


def generate_chat_response(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: Optional[float] = None,
) -> Dict[str, str]:
    """Unified entrypoint for generating structured chat responses.

    Args:
        prompt: Student's natural language question.
        system_prompt: Optional system prompt instructions.
        provider: Provider name ("groq", "gemini", or "mock").
        model: Specific model identifier.
        temperature: Sampling temperature.
        max_tokens: Token budget limit.
        timeout: Network timeout in seconds.

    Returns:
        Dictionary with strictly validated keys: "answer", "confidence", "follow_up".
    """
    sys_prompt = system_prompt or load_system_prompt()
    selected_provider = (provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)).lower()
    temp = temperature if temperature is not None else DEFAULT_TEMPERATURE
    tokens = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
    req_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT

    # Determine fallback behavior if provider credentials aren't present
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if selected_provider == "groq":
        if not groq_key or groq_key.startswith("gsk_your_groq"):
            logger.warning("Groq selected but valid GROQ_API_KEY not found. Using Mock provider.")
            return call_mock_provider(prompt)
        selected_model = model or DEFAULT_GROQ_MODEL
        return call_groq(prompt, sys_prompt, selected_model, temp, tokens, req_timeout)

    elif selected_provider == "gemini":
        if not gemini_key or gemini_key.startswith("AIzaSy_your_gemini"):
            logger.warning("Gemini selected but valid GEMINI_API_KEY not found. Using Mock provider.")
            return call_mock_provider(prompt)
        selected_model = model or DEFAULT_GEMINI_MODEL
        return call_gemini(prompt, sys_prompt, selected_model, temp, tokens, req_timeout)

    elif selected_provider == "mock":
        return call_mock_provider(prompt)

    else:
        logger.warning("Unrecognized provider '%s'. Falling back to mock provider.", selected_provider)
        return call_mock_provider(prompt)
