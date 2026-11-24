"""Retrieval-Augmented Generation (RAG) module for KubeCoach.

Implements an end-to-end grounded RAG pipeline:
1. Embeds incoming Kubernetes user questions.
2. Retrieves top-k relevant documentation chunks from persistent ChromaDB storage.
3. Evaluates context sufficiency using a generalized relevance and domain coverage rule.
4. Generates an answer strictly grounded in the retrieved documentation context.
5. Emits verifiable citations referencing official Kubernetes documents.
6. Refuses out-of-scope or unanswerable queries with an honest 'I don't know' and zero fake citations.
"""

from dataclasses import asdict, dataclass, field
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.llm import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROVIDER,
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT,
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    call_gemini,
    call_groq,
    extract_structured_json,
)
from app.vectorstore import KubeCoachVectorStore, VectorStoreError, get_vector_store

logger = logging.getLogger("kubecoach.rag")

BASE_DIR = Path(__file__).resolve().parent.parent
RAG_PROMPT_PATH = BASE_DIR / "prompts" / "rag_system_prompt.md"

# Standard English stop words for context sufficiency checking
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "aren't", "as", "at", "be", "because", "been", "before", "being", "below", "between", "both",
    "but", "by", "can", "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does",
    "doesn't", "doing", "don't", "down", "during", "each", "few", "for", "from", "further", "had",
    "hadn't", "has", "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "i", "i'd", "i'll",
    "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off", "on", "once",
    "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same",
    "shan't", "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves", "then", "there",
    "there's", "these", "they", "they'd", "they'll", "they're", "they've", "this", "those", "through",
    "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're",
    "we've", "were", "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves",
}


@dataclass
class Citation:
    """Represents a citation referencing a retrieved documentation source."""

    document_title: str
    source_url: str
    page: str
    chunk_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert citation to dictionary representation."""
        data = asdict(self)
        if self.chunk_id is None:
            data.pop("chunk_id", None)
        return data


@dataclass
class RAGResult:
    """Encapsulates the complete result of a RAG query execution."""

    question: str
    answer: str
    citations: List[Citation] = field(default_factory=list)
    retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)
    confidence: str = "medium"
    context_sufficient: bool = True
    provider: str = "mock"
    model: str = "grounded-local-kb"

    def to_dict(self) -> Dict[str, Any]:
        """Convert RAGResult to a dictionary conforming to the API response schema."""
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "retrieved_chunks": self.retrieved_chunks,
            "confidence": self.confidence,
            "context_sufficient": self.context_sufficient,
            "provider": self.provider,
            "model": self.model,
        }


def load_rag_prompt(path: Optional[Path] = None) -> str:
    """Read the master grounded RAG system prompt."""
    target = path or RAG_PROMPT_PATH
    if target.is_file():
        return target.read_text(encoding="utf-8").strip()
    return (
        "You are KubeCoach, an educational Kubernetes AI assistant. Answer the user's question "
        "using ONLY the retrieved documentation context. If the context does not contain the answer, "
        "respond with 'I don't know based on the provided official Kubernetes documentation.' "
        "Return JSON with 'answer', 'confidence', and 'citations'."
    )


def extract_keywords(text: str) -> List[str]:
    """Extract lowercased non-stopword alphanumeric tokens from text."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def is_context_sufficient(
    query: str,
    chunks: List[Dict[str, Any]],
    min_similarity_threshold: float = 0.55,
) -> Tuple[bool, str]:
    """Evaluate whether the retrieved context contains sufficient information for the query.

    General Principle:
    1. If no chunks were returned, context is insufficient.
    2. If the maximum similarity of all retrieved chunks is below `min_similarity_threshold`,
       the documents are semantically too distant.
    3. If the query asks about technical entities or topics completely absent from the
       entire retrieved corpus (e.g. Istio, service mesh, Nomad), the question is out of scope.

    Returns:
        Tuple of (is_sufficient: bool, reason: str)
    """
    if not chunks:
        return False, "No documentation chunks were retrieved from the vector store."

    max_similarity = max((c.get("similarity", 0.0) for c in chunks), default=0.0)
    if max_similarity < min_similarity_threshold:
        return (
            False,
            f"Top retrieved chunk similarity ({max_similarity:.4f}) is below threshold ({min_similarity_threshold:.2f}).",
        )

    # Combine text from all retrieved chunks for vocabulary coverage analysis
    combined_context_text = " ".join(c.get("text", "").lower() for c in chunks)
    combined_titles = " ".join(c.get("title", "").lower() for c in chunks)
    corpus = f"{combined_titles} {combined_context_text}"

    query_keywords = extract_keywords(query)
    if not query_keywords:
        return True, "Query has general phrasing; top similarity is adequate."

    # Known out-of-scope technologies for core Kubernetes
    out_of_scope_terms = {
        "istio", "envoy", "consul", "nomad", "linkerd", "openshift", "rancher",
        "mesos", "swarm", "terraform", "ansible", "argo", "flux",
    }
    for term in out_of_scope_terms:
        if term in query.lower() and term not in corpus:
            return (
                False,
                f"Query specifies out-of-scope technology '{term}', which is not present in retrieved context.",
            )

    # Check key technical nouns from query
    matched_keywords = [kw for kw in query_keywords if kw in corpus]
    coverage = len(matched_keywords) / len(query_keywords)

    # If none of the query's keywords appear in the retrieved text, the question is unrelated to the
    # retrieved documents even when the vector similarity looks moderate (e.g. "capital of France").
    if not matched_keywords:
        return (
            False,
            f"None of the query keywords ({', '.join(query_keywords[:5])}) appear in the retrieved context.",
        )

    # If less than 25% of query keywords appear anywhere in retrieved chunks, context is insufficient
    if coverage < 0.25 and len(query_keywords) >= 3:
        return (
            False,
            f"Keyword coverage is too low ({len(matched_keywords)}/{len(query_keywords)} matched).",
        )

    return True, f"Context verified (max similarity: {max_similarity:.4f}, coverage: {coverage:.2f})."


def format_context_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into numbered context blocks for LLM injection."""
    if not chunks:
        return "No retrieved documentation context available."

    blocks: List[str] = []
    for idx, c in enumerate(chunks, start=1):
        title = c.get("title", "Kubernetes Documentation")
        page = c.get("page", "unknown")
        source_url = c.get("source_url", c.get("source", "https://kubernetes.io/docs/concepts/"))
        text = c.get("text", "").strip()

        block = (
            f"--- [Context Block {idx}] ---\n"
            f"Document Title: {title}\n"
            f"Page / File: {page}\n"
            f"Source URL: {source_url}\n"
            f"Content:\n{text}\n"
        )
        blocks.append(block)

    return "\n".join(blocks)


def build_citations(chunks: List[Dict[str, Any]]) -> List[Citation]:
    """Construct deduplicated Citation objects from retrieved chunks."""
    citations: List[Citation] = []
    seen: Set[Tuple[str, str]] = set()

    for c in chunks:
        title = c.get("title") or c.get("page", "Kubernetes Documentation")
        source_url = c.get("source_url") or c.get("source") or "https://kubernetes.io/docs/concepts/"
        page = c.get("page", "doc")
        chunk_id = c.get("chunk_id")

        key = (title.strip().lower(), source_url.strip().lower())
        if key not in seen:
            seen.add(key)
            citations.append(
                Citation(
                    document_title=title,
                    source_url=source_url,
                    page=page,
                    chunk_id=chunk_id,
                )
            )

    return citations


def generate_mock_rag_answer(
    question: str,
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deterministic, grounded mock answer generator for offline development and testing.

    Extracts definitions, kubectl commands, and key facts directly from top retrieved chunks.
    """
    if not chunks:
        return {
            "answer": "I don't know based on the provided official Kubernetes documentation.",
            "confidence": "low",
            "citations": [],
        }

    top_chunk = chunks[0]
    top_text = top_chunk.get("text", "").strip()
    title = top_chunk.get("title", "Kubernetes Object")
    category = top_chunk.get("category", "concept")

    # Look for kubectl commands in the chunk text
    cmd_match = re.search(r"(kubectl\s+[a-zA-Z0-9\-\_\s\./=]+)", top_text)
    cmd_snippet = f"\n\nExample command:\n```bash\n{cmd_match.group(1).strip()}\n```" if cmd_match else ""

    # Extract first 2-3 substantive sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", top_text) if len(s.strip()) > 15]
    summary_body = " ".join(sentences[:3]) if sentences else top_text[:250]

    answer = (
        f"Based on official Kubernetes documentation for {title} ({category}):\n\n"
        f"{summary_body}{cmd_snippet}"
    )

    citations = build_citations(chunks[:2])
    return {
        "answer": answer,
        "confidence": "high",
        "citations": [c.to_dict() for c in citations],
    }


def execute_rag_pipeline(
    question: str,
    top_k: int = 3,
    vector_store: Optional[KubeCoachVectorStore] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    min_similarity: float = 0.55,
) -> RAGResult:
    """Execute the complete Retrieval-Augmented Generation pipeline.

    Args:
        question: User query string.
        top_k: Number of chunks to retrieve (default 3).
        vector_store: Vector store instance (defaults to singleton get_vector_store()).
        provider: LLM provider override ('groq', 'gemini', or 'mock').
        model: Specific model identifier.
        system_prompt: Optional override for RAG system prompt.
        min_similarity: Minimum similarity threshold for context sufficiency.

    Returns:
        Structured RAGResult dataclass instance.
    """
    clean_query = question.strip() if question else ""
    if not clean_query:
        return RAGResult(
            question="",
            answer="I don't know based on the provided official Kubernetes documentation. The question was empty.",
            citations=[],
            retrieved_chunks=[],
            confidence="low",
            context_sufficient=False,
            provider="system",
            model="none",
        )

    # 1. Retrieve relevant chunks from persistent ChromaDB vector store
    store = vector_store or get_vector_store()
    try:
        retrieved_chunks = store.query_similar(query_text=clean_query, n_results=top_k)
    except Exception as exc:
        logger.error("Vector store retrieval error during RAG execution: %s", exc)
        raise VectorStoreError(f"Vector search failed: {exc}") from exc

    # 2. Evaluate context sufficiency
    sufficient, reason = is_context_sufficient(
        query=clean_query,
        chunks=retrieved_chunks,
        min_similarity_threshold=min_similarity,
    )
    logger.info("Context sufficiency check for '%s': sufficient=%s (%s)", clean_query, sufficient, reason)

    # 3. Handle unanswerable / insufficient context with honest refusal
    if not sufficient:
        return RAGResult(
            question=clean_query,
            answer="I don't know based on the provided official Kubernetes documentation. The retrieved documents do not contain sufficient information to answer this question.",
            citations=[],
            retrieved_chunks=retrieved_chunks,
            confidence="low",
            context_sufficient=False,
            provider="kubecoach-guardrail",
            model="context-sufficiency-rule",
        )

    # 4. Determine LLM provider and credentials
    selected_provider = (provider or os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)).lower()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    active_provider = selected_provider
    if selected_provider == "groq" and (not groq_key or groq_key.startswith("gsk_your_groq")):
        active_provider = "mock"
    elif selected_provider == "gemini" and (not gemini_key or gemini_key.startswith("AIzaSy_your_gemini")):
        active_provider = "mock"

    sys_prompt = system_prompt or load_rag_prompt()
    formatted_context = format_context_for_prompt(retrieved_chunks)

    # 5. Execute generation
    if active_provider == "mock":
        mock_output = generate_mock_rag_answer(question=clean_query, chunks=retrieved_chunks)
        citations = build_citations(retrieved_chunks)
        return RAGResult(
            question=clean_query,
            answer=mock_output["answer"],
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence=mock_output.get("confidence", "high"),
            context_sufficient=True,
            provider="mock",
            model="grounded-local-kb",
        )

    user_prompt = (
        f"Retrieved Documentation Context:\n{formatted_context}\n\n"
        f"User Question: {clean_query}\n\n"
        "Provide a grounded explanation based ONLY on the retrieved documentation context above. "
        "Include actionable kubectl commands and official citations."
    )

    try:
        if active_provider == "groq":
            sel_model = model or DEFAULT_GROQ_MODEL
            response_dict = call_groq(
                prompt=user_prompt,
                system_prompt=sys_prompt,
                model=sel_model,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
                timeout=DEFAULT_TIMEOUT,
            )
        elif active_provider == "gemini":
            sel_model = model or DEFAULT_GEMINI_MODEL
            response_dict = call_gemini(
                prompt=user_prompt,
                system_prompt=sys_prompt,
                model=sel_model,
                temperature=DEFAULT_TEMPERATURE,
                max_tokens=DEFAULT_MAX_TOKENS,
                timeout=DEFAULT_TIMEOUT,
            )
        else:
            sel_model = "grounded-local-kb"
            response_dict = generate_mock_rag_answer(question=clean_query, chunks=retrieved_chunks)

        answer_text = response_dict.get("answer", "").strip()
        confidence = response_dict.get("confidence", "high").lower()

        # Check if the LLM self-reported an unanswerable status
        refusal_patterns = ["i don't know", "i do not know", "not provided in the context", "cannot answer"]
        if any(rp in answer_text.lower() for rp in refusal_patterns):
            return RAGResult(
                question=clean_query,
                answer=answer_text,
                citations=[],
                retrieved_chunks=retrieved_chunks,
                confidence="low",
                context_sufficient=False,
                provider=active_provider,
                model=sel_model,
            )

        citations = build_citations(retrieved_chunks)
        return RAGResult(
            question=clean_query,
            answer=answer_text,
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence=confidence,
            context_sufficient=True,
            provider=active_provider,
            model=sel_model,
        )

    except (LLMAuthenticationError, LLMRateLimitError, LLMTimeoutError, LLMError):
        # Re-raise explicit LLM errors so FastAPI endpoints can return proper status codes
        raise
    except Exception as exc:
        logger.warning("LLM call failed with error (%s). Falling back to grounded mock.", exc)
        mock_output = generate_mock_rag_answer(question=clean_query, chunks=retrieved_chunks)
        citations = build_citations(retrieved_chunks)
        return RAGResult(
            question=clean_query,
            answer=mock_output["answer"],
            citations=citations,
            retrieved_chunks=retrieved_chunks,
            confidence="medium",
            context_sufficient=True,
            provider="mock-fallback",
            model="grounded-local-kb",
        )
