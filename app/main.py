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

# Initialize ChromaDB and optional HNSW runtime before other C-extensions (e.g. scikit-learn / OpenMP)
try:
    import hnswlib  # noqa: F401
except ImportError:
    pass
import chromadb
from app.vectorstore import VectorStoreError, get_vector_store

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


@app.on_event("startup")
def startup_event() -> None:
    """Initialize and warm up ChromaDB vector store on the main thread."""
    try:
        from app.vectorstore import get_vector_store

        store = get_vector_store()
        store.get_collection()
    except Exception as exc:
        logger.warning("Vector store startup warmup failed: %s", exc)

QUESTIONS_FILE_PATH = REPO_ROOT / "data" / "questions.json"
FEEDBACK_FILE_PATH = REPO_ROOT / "data" / "feedback.json"


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


class SemanticSearchResult(BaseModel):
    """Schema for individual semantic vector search match."""

    chunk_id: str = Field(..., description="Unique chunk identifier.")
    text: str = Field(..., description="Extracted text chunk content.")
    similarity: float = Field(..., description="Cosine similarity score (0.0 to 1.0).")
    distance: float = Field(..., description="Vector distance score.")
    source: str = Field(..., description="Originating document path or URL.")
    page: str = Field(..., description="Page slug or record identifier.")
    title: str = Field(..., description="Document or concept title.")
    category: str = Field(default="general", description="Concept category.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Full chunk metadata attributes.")


class SemanticSearchResponse(BaseModel):
    """Schema for semantic vector search response."""

    query: str = Field(..., description="The original search query.")
    total_results: int = Field(..., description="Number of retrieved chunks.")
    results: List[SemanticSearchResult] = Field(default_factory=list, description="Ranked relevant chunks.")


class HealthResponse(BaseModel):
    """Schema for API health status."""

    status: str
    app: str
    version: str
    records_count: int


class CitationItem(BaseModel):
    """Schema for a documentation source citation."""

    document_title: str = Field(..., description="Title of the cited Kubernetes document or concept.")
    source_url: str = Field(..., description="Official documentation source URL.")
    page: str = Field(..., description="Document page or source file.")
    chunk_id: Optional[str] = Field(default=None, description="Optional chunk identifier.")


class AskRequest(BaseModel):
    """Schema for incoming RAG question request."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The Kubernetes question to answer using grounded RAG.",
        example="What is a Pod and what command lists running pods?",
    )
    top_k: Optional[int] = Field(
        default=3,
        ge=1,
        le=20,
        description="Number of relevant document chunks to retrieve.",
        example=3,
    )


class AskResponse(BaseModel):
    """Schema for grounded RAG response with citations and retrieved chunks."""

    question: str = Field(..., description="The original student question.")
    answer: str = Field(..., description="Grounded plain-English explanation.")
    citations: List[CitationItem] = Field(default_factory=list, description="Verified documentation citations.")
    retrieved_chunks: List[Dict[str, Any]] = Field(default_factory=list, description="Raw chunks retrieved from vector store.")
    confidence: str = Field(..., description="Confidence level: high, medium, or low.")
    context_sufficient: bool = Field(..., description="Whether retrieved context was sufficient to answer.")


class AgentRequest(BaseModel):
    """Schema for incoming AI Agent request or approval resume via POST /agent."""

    question: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="The Kubernetes inquiry, kubectl command, or quantity conversion request. Optional when resuming an interrupted approval with session_id + approved.",
        example="Convert 500m CPU to cores",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional persistent thread/session identifier for LangGraph MemorySaver.",
        example="sess-a1b2c3d4",
    )
    approved: Optional[bool] = Field(
        default=None,
        description="Human approval response (true/false) when resuming a paused LangGraph interrupt.",
        example=True,
    )


class AgentApprovalRequest(BaseModel):
    """Schema for dedicated human-in-the-loop approval resume endpoint (POST /agent/approve)."""

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Session ID currently paused awaiting human approval.",
        example="sess-a1b2c3d4",
    )
    approved: bool = Field(
        ...,
        description="True to approve and execute the proposed tool; False to reject cleanly.",
        example=True,
    )


class AgentResponse(BaseModel):
    """Schema for AI Agent execution response."""

    question: str = Field(..., description="The user question or request.")
    answer: str = Field(..., description="Synthesized grounded answer or approval prompt/rejection message.")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Ordered list of executed tool calls.")
    citations: List[Dict[str, Any]] = Field(default_factory=list, description="Official Kubernetes documentation citations.")
    session_id: str = Field(..., description="Session/thread identifier for multi-turn memory and resume.")
    approval_required: bool = Field(..., description="Whether LangGraph execution is currently paused awaiting approval.")
    approval_status: str = Field(default="not_required", description="Approval status: not_required, pending, approved, or rejected.")
    pending_tool: Optional[Dict[str, Any]] = Field(default=None, description="Proposed tool name and exact arguments awaiting approval.")
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list, description="Structured step-by-step execution trace.")
    iteration_count: int = Field(default=0, description="Number of reasoning cycles executed in this turn.")
    success: bool = Field(default=True, description="Whether the request succeeded.")


class FeedbackRequest(BaseModel):
    """Schema for persistent user thumbs-up / thumbs-down feedback on an assistant answer."""

    response_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique identifier for the assistant response being rated.",
        example="resp-1a2b3c4d",
    )
    session_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Chat session identifier associated with the response.",
        example="sess-a1b2c3d4",
    )
    feedback: str = Field(
        ...,
        description="Feedback rating: 'up' (helpful) or 'down' (not helpful).",
        example="up",
    )
    question: Optional[str] = Field(
        default="",
        max_length=1000,
        description="Original student question associated with this response.",
    )
    mode: Optional[str] = Field(
        default="rag",
        max_length=32,
        description="Assistant mode used ('rag' or 'agent').",
    )


class FeedbackResponse(BaseModel):
    """Schema returned after recording feedback persistently."""

    status: str
    feedback_id: str
    response_id: str
    session_id: str
    feedback: str
    mode: str
    timestamp: str


@app.get("/", tags=["General"])
def root() -> Dict[str, str]:
    """Root welcome endpoint providing links to documentation."""
    return {
        "message": "Welcome to the KubeCoach API — Kubernetes Educational Assistant",
        "docs_url": "/docs",
        "health_url": "/health",
        "search_url": "/search?q=pod",
        "semantic_search_url": "/search/semantic?q=pod",
        "chat_url": "/chat",
        "ask_url": "/ask",
        "agent_url": "/agent",
        "agent_approve_url": "/agent/approve",
        "feedback_url": "/feedback",
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
    from app.smart_search import smart_search
    results = smart_search(cleaned, records=records, top_k=3)
    return results


@app.get(
    "/search/semantic",
    response_model=SemanticSearchResponse,
    status_code=status.HTTP_200_OK,
    tags=["Search"],
)
async def search_semantic_endpoint(
    q: str = Query(
        ...,
        min_length=1,
        max_length=500,
        description="Search query to match against chunked documents using dense semantic embeddings.",
    ),
    limit: int = Query(
        default=3,
        ge=1,
        le=20,
        description="Maximum number of relevant chunks to retrieve.",
    ),
    category: Optional[str] = Query(
        default=None,
        description="Optional category filter (e.g. 'workload', 'networking', 'storage').",
    ),
) -> SemanticSearchResponse:
    """Perform dense semantic vector search across persistent ChromaDB storage."""
    cleaned = q.strip()
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Search query cannot be empty or whitespace only.",
        )

    try:
        from app.vectorstore import VectorStoreError, get_vector_store

        store = get_vector_store()
        # If vector store is empty, trigger initial indexing
        if store.count() == 0:
            logger.info("ChromaDB vector store is empty; running initial document indexing...")
            store.index_documents()

        category_filter = category.strip() if isinstance(category, str) and category.strip() else None

        raw_results = store.query_similar(
            query_text=cleaned,
            n_results=limit,
            category=category_filter,
        )

        formatted = [
            SemanticSearchResult(
                chunk_id=r["chunk_id"],
                text=r["text"],
                similarity=r["similarity"],
                distance=r["distance"],
                source=r["source"],
                page=r["page"],
                title=r["title"],
                category=r.get("category", "general"),
                metadata=r.get("metadata", {}),
            )
            for r in raw_results
        ]

        return SemanticSearchResponse(
            query=cleaned,
            total_results=len(formatted),
            results=formatted,
        )
    except VectorStoreError as vs_err:
        logger.error("Vector store error during semantic search: %s", vs_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Semantic search service unavailable: {vs_err}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in /search/semantic: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred during semantic search.",
        )


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


@app.post(
    "/ask",
    response_model=AskResponse,
    status_code=status.HTTP_200_OK,
    tags=["RAG"],
)
def ask_kubecoach_rag(payload: AskRequest) -> AskResponse:
    """Answer a Kubernetes question using Retrieval-Augmented Generation with citations.

    Retrieves top-k documentation chunks from persistent ChromaDB, evaluates context
    sufficiency, and generates a grounded response with official citations.
    """
    question_text = payload.question.strip()
    if not question_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty or whitespace only.",
        )

    top_k = payload.top_k if payload.top_k is not None else 3
    if top_k < 1 or top_k > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="top_k must be between 1 and 20.",
        )

    logger.info("RAG ask request received: '%s' (top_k=%d)", question_text, top_k)

    try:
        from app.rag import execute_rag_pipeline

        rag_result = execute_rag_pipeline(
            question=question_text,
            top_k=top_k,
        )

        citation_items = [
            CitationItem(
                document_title=c.document_title,
                source_url=c.source_url,
                page=c.page,
                chunk_id=c.chunk_id,
            )
            for c in rag_result.citations
        ]

        return AskResponse(
            question=rag_result.question,
            answer=rag_result.answer,
            citations=citation_items,
            retrieved_chunks=rag_result.retrieved_chunks,
            confidence=rag_result.confidence,
            context_sufficient=rag_result.context_sufficient,
        )

    except VectorStoreError as vs_err:
        logger.error("Vector store error during /ask: %s", vs_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Vector search service unavailable: {vs_err}",
        )
    except LLMAuthenticationError as auth_err:
        logger.error("LLM authentication failure during /ask: %s", auth_err)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM authentication error: {auth_err}",
        )
    except LLMRateLimitError as rate_err:
        logger.warning("LLM rate limit hit during /ask: %s", rate_err)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="LLM rate limit exceeded. Please wait a moment before trying again.",
        )
    except LLMTimeoutError as timeout_err:
        logger.error("LLM timeout during /ask: %s", timeout_err)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="LLM request timed out while generating RAG answer.",
        )
    except LLMError as llm_err:
        logger.error("LLM provider error during /ask: %s", llm_err)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider error: {llm_err}",
        )
    except Exception as exc:
        logger.exception("Unexpected error in /ask endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while processing RAG request.",
        )


def _build_agent_response(result: Dict[str, Any], fallback_question: str = "") -> AgentResponse:
    """Convert raw LangGraph response dict to validated AgentResponse schema."""
    return AgentResponse(
        question=result.get("question", fallback_question),
        answer=result.get("answer", ""),
        tool_calls=result.get("tool_calls", []),
        citations=result.get("citations", []),
        session_id=result.get("session_id", ""),
        approval_required=bool(result.get("approval_required", False)),
        approval_status=str(result.get("approval_status") or "not_required"),
        pending_tool=result.get("pending_tool"),
        execution_trace=result.get("execution_trace", []),
        iteration_count=int(result.get("iteration_count", 0)),
        success=bool(result.get("success", True)),
    )


@app.post(
    "/agent",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Agent"],
)
def run_kubecoach_agent_endpoint(payload: AgentRequest) -> AgentResponse:
    """Execute or resume the KubeCoach LangGraph stateful agent workflow.

    Supports:
    - Autonomous RAG documentation retrieval with verifiable citations.
    - Human-in-the-loop interrupt/resume approval for `k8s_quantity_converter`.
    - Persistent, isolated multi-turn memory via LangGraph `MemorySaver`.
    """
    question_text = (payload.question or "").strip()
    session_id = payload.session_id.strip() if payload.session_id and payload.session_id.strip() else None

    # Allow resuming a paused approval without repeating the question
    is_resume_only = (not question_text) and (session_id is not None) and (payload.approved is not None)
    if not question_text and not is_resume_only:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Question cannot be empty or whitespace only (unless resuming an approval with session_id and approved).",
        )

    logger.info(
        "Agent request received: question='%s', session_id=%s, approved=%s",
        question_text,
        session_id,
        payload.approved,
    )

    try:
        from app.graph import has_pending_approval, resume_agent_approval, run_agent

        if is_resume_only:
            if not has_pending_approval(session_id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"No pending human approval found for session_id '{session_id}'.",
                )
            result = resume_agent_approval(session_id=session_id, approved=bool(payload.approved))
        else:
            result = run_agent(
                question=question_text,
                session_id=session_id,
                approved=payload.approved,
            )

        return _build_agent_response(result, fallback_question=question_text)

    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.exception("Error executing /agent endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while executing the agent workflow.",
        )


@app.post(
    "/agent/approve",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    tags=["Agent"],
)
def approve_kubecoach_agent_endpoint(payload: AgentApprovalRequest) -> AgentResponse:
    """Resume an interrupted KubeCoach LangGraph session with explicit human approval or rejection."""
    sid = payload.session_id.strip()
    if not sid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id cannot be empty or whitespace only.",
        )

    logger.info("Agent approval decision received: session_id='%s', approved=%s", sid, payload.approved)

    try:
        from app.graph import has_pending_approval, resume_agent_approval

        if not has_pending_approval(sid):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"No pending human approval found for session_id '{sid}'.",
            )

        result = resume_agent_approval(session_id=sid, approved=payload.approved)
        return _build_agent_response(result)

    except HTTPException:
        raise
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.exception("Error executing /agent/approve endpoint: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal server error occurred while resuming agent approval.",
        )


def _load_feedback_records() -> List[Dict[str, Any]]:
    """Safely load persisted feedback records from FEEDBACK_FILE_PATH."""
    if not FEEDBACK_FILE_PATH.exists():
        return []
    try:
        raw = FEEDBACK_FILE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not parse feedback file (%s); starting fresh list.", exc)
        return []


def _save_feedback_records(records: List[Dict[str, Any]]) -> None:
    """Safely write feedback records to FEEDBACK_FILE_PATH using UTF-8 JSON."""
    FEEDBACK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEEDBACK_FILE_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")


@app.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Feedback"],
)
def submit_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    """Persist thumbs-up / thumbs-down feedback to data/feedback.json.

    Prevents duplicate feedback submissions for the same (session_id, response_id).
    Never stores API keys or sensitive credentials.
    """
    response_id = payload.response_id.strip()
    session_id = payload.session_id.strip()
    raw_feedback = payload.feedback.strip().lower()
    mode = (payload.mode or "rag").strip().lower()
    question_text = (payload.question or "").strip()

    if not response_id or not session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="response_id and session_id cannot be empty or whitespace only.",
        )

    feedback_map = {
        "up": "up",
        "thumbs_up": "up",
        "helpful": "up",
        "down": "down",
        "thumbs_down": "down",
        "not_helpful": "down",
    }
    normalized_feedback = feedback_map.get(raw_feedback)
    if not normalized_feedback:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="feedback must be 'up' (helpful) or 'down' (not_helpful).",
        )

    if mode not in ("rag", "agent"):
        mode = "rag"

    records = _load_feedback_records()

    # Prevent duplicate submission for the same response in the same session
    for existing in records:
        if existing.get("response_id") == response_id and existing.get("session_id") == session_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Feedback already submitted for response_id '{response_id}'.",
            )

    feedback_id = f"fb-{uuid.uuid4().hex[:8]}"
    timestamp = datetime.utcnow().isoformat() + "Z"

    entry = {
        "feedback_id": feedback_id,
        "response_id": response_id,
        "session_id": session_id,
        "question": question_text[:500],
        "feedback": normalized_feedback,
        "mode": mode,
        "timestamp": timestamp,
    }
    records.append(entry)

    try:
        _save_feedback_records(records)
    except OSError as exc:
        logger.error("Failed to persist feedback record: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save feedback to storage.",
        )

    logger.info(
        "Saved feedback [%s] (%s) for response '%s' in session '%s'",
        feedback_id,
        normalized_feedback,
        response_id,
        session_id,
    )
    return FeedbackResponse(
        status="saved",
        feedback_id=feedback_id,
        response_id=response_id,
        session_id=session_id,
        feedback=normalized_feedback,
        mode=mode,
        timestamp=timestamp,
    )


@app.get("/feedback", tags=["Feedback"])
def list_feedback() -> Dict[str, Any]:
    """Return aggregate feedback counts and stored entries (non-sensitive)."""
    records = _load_feedback_records()
    helpful = sum(1 for r in records if r.get("feedback") == "up")
    not_helpful = sum(1 for r in records if r.get("feedback") == "down")
    return {
        "total": len(records),
        "helpful": helpful,
        "not_helpful": not_helpful,
        "items": records,
    }



