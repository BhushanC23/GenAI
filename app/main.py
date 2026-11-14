"""FastAPI backend application for KubeCoach.

Exposes RESTful endpoints for health status, querying Kubernetes records,
TF-IDF smart search, student question submission, and LLM-powered educational chat.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import uuid

# Ensure repository root is on sys.path for direct module execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    generate_chat_response,
)
from app.records import get_by_id, load_records
from app.smart_search import smart_search

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kubecoach.api")

app = FastAPI(
    title="KubeCoach API",
    description="Educational API providing beginner-friendly Kubernetes concepts, kubectl commands, and smart search.",
    version="1.0.0",
)

QUESTIONS_FILE_PATH = REPO_ROOT / "data" / "questions.json"


# Pydantic Schemas
class QuestionRequest(BaseModel):
    """Schema for incoming student question submission."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The Kubernetes question asked by the student.",
        example="What is the difference between a Pod and a Deployment?",
    )
    user_name: Optional[str] = Field(
        default="Anonymous",
        max_length=100,
        description="Optional name or registration ID of the student.",
        example="Bhushan",
    )


class QuestionResponse(BaseModel):
    """Schema for response after saving a question."""

    status: str
    question_id: str
    question: str
    user_name: str
    timestamp: str


class ChatRequest(BaseModel):
    """Schema for student chat prompt sent to the LLM assistant."""

    question: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="The Kubernetes concept or command question to ask KubeCoach.",
        example="What is a Pod and how do I inspect its logs?",
    )
    user_name: Optional[str] = Field(
        default="Anonymous",
        max_length=100,
        description="Optional user name or student ID.",
        example="Bhushan",
    )


class ChatResponse(BaseModel):
    """Structured response schema returned by KubeCoach LLM."""

    answer: str = Field(..., description="Plain-English explanation with kubectl commands.")
    confidence: str = Field(..., description="Confidence level: high, medium, or low.")
    follow_up: str = Field(..., description="A helpful next question to test understanding.")


class HealthResponse(BaseModel):
    """Schema for API health status."""

    status: str
    app: str
    version: str
    records_count: int


@app.get("/", tags=["General"])
def root() -> Dict[str, str]:
    """Root welcome endpoint providing links to documentation."""
    return {
        "message": "Welcome to the KubeCoach API — Kubernetes Educational Assistant",
        "docs_url": "/docs",
        "health_url": "/health",
        "search_url": "/search?q=pod",
        "chat_url": "/chat",
    }


@app.get("/health", response_model=HealthResponse, tags=["Monitoring"])
def get_health() -> HealthResponse:
    """Return API health status and number of loaded knowledge records."""
    records = load_records()
    return HealthResponse(
        status="ok",
        app="KubeCoach API",
        version="1.0.0",
        records_count=len(records),
    )


@app.get("/records", tags=["Records"])
def get_records(
    limit: Optional[int] = Query(
        default=None,
        ge=1,
        le=100,
        description="Optional maximum number of records to return.",
    )
) -> List[Dict[str, Any]]:
    """Return all available Kubernetes records, optionally limited."""
    records = load_records()
    if limit is not None:
        return records[:limit]
    return records


@app.get("/records/{record_id}", tags=["Records"])
def get_record_by_id(record_id: str) -> Dict[str, Any]:
    """Return a single Kubernetes record by its ID, or HTTP 404 if not found."""
    records = load_records()
    record = get_by_id(records, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Record with ID '{record_id}' not found.",
        )
    return record


@app.get("/search", tags=["Search"])
def search_records(
    q: str = Query(
        default="",
        description="Search query to match against Kubernetes records using TF-IDF.",
    )
) -> List[Dict[str, Any]]:
    """Search Kubernetes records using TF-IDF vectorization and cosine similarity."""
    cleaned = q.strip()
    if not cleaned:
        return []

    records = load_records()
    results = smart_search(cleaned, records=records, top_k=3)
    return results


@app.post(
    "/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Questions"],
)
def submit_question(payload: QuestionRequest) -> QuestionResponse:
    """Accept a user question and persist it to data/questions.json."""
    question_text = payload.question.strip()
    user_name = (payload.user_name or "Anonymous").strip()

    QUESTIONS_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Read existing questions safely
    questions_list: List[Dict[str, Any]] = []
    if QUESTIONS_FILE_PATH.exists():
        try:
            content = QUESTIONS_FILE_PATH.read_text(encoding="utf-8")
            if content.strip():
                questions_list = json.loads(content)
                if not isinstance(questions_list, list):
                    questions_list = []
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read existing questions.json: %s", exc)
            questions_list = []

    new_id = f"q-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.utcnow().isoformat() + "Z"

    entry = {
        "question_id": new_id,
        "question": question_text,
        "user_name": user_name,
        "timestamp": timestamp,
    }
    questions_list.append(entry)

    try:
        QUESTIONS_FILE_PATH.write_text(
            json.dumps(questions_list, indent=2), encoding="utf-8"
        )
        logger.info("Saved new question [%s] from '%s'", new_id, user_name)
    except OSError as exc:
        logger.error("Failed to write to %s: %s", QUESTIONS_FILE_PATH, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save question to storage.",
        )

    return QuestionResponse(
        status="saved",
        question_id=new_id,
        question=question_text,
        user_name=user_name,
        timestamp=timestamp,
    )


@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    tags=["Chat"],
)
def chat_with_kubecoach(payload: ChatRequest) -> ChatResponse:
    """Ask KubeCoach a question and receive structured explanation with kubectl commands."""
    question_text = payload.question.strip()
    logger.info("Chat request received from '%s': %s", payload.user_name, question_text)

    try:
        response_dict = generate_chat_response(prompt=question_text)
        return ChatResponse(
            answer=response_dict["answer"],
            confidence=response_dict["confidence"],
            follow_up=response_dict["follow_up"],
        )
    except LLMAuthenticationError as auth_err:
        logger.error("LLM authentication failure: %s", auth_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM provider authentication error: {auth_err}",
        )
    except LLMRateLimitError as rate_err:
        logger.warning("LLM rate limit hit: %s", rate_err)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM provider rate limit exceeded. Please wait a moment before trying again.",
        )
    except LLMTimeoutError as timeout_err:
        logger.error("LLM timeout: %s", timeout_err)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM provider request timed out. Please try again.",
        )
    except LLMError as llm_err:
        logger.error("LLM provider error: %s", llm_err)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {llm_err}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in /chat endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while generating response.",
        )
