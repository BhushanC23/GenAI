"""Embedding module for KubeCoach.

Provides a modular interface for transforming text chunks and search queries
into dense numerical vector embeddings. Uses the lightweight Sentence Transformers
model `all-MiniLM-L6-v2` (384 dimensions) by default, with lazy loading, batching,
and fallback support.
"""

from abc import ABC, abstractmethod
import hashlib
import logging
import math
import os
from typing import List, Optional, Union

logger = logging.getLogger("kubecoach.embed")

DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class BaseEmbeddingProvider(ABC):
    """Abstract interface for embedding generation."""

    @abstractmethod
    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Embed a list of text strings into vectors."""

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string into a vector."""

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the vector dimensionality."""


class SentenceTransformerEmbedder(BaseEmbeddingProvider):
    """Local embedding provider using SentenceTransformers."""

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self._model = None
        self._dimension = EMBEDDING_DIMENSION

    def _load_model(self):
        """Lazy load the sentence-transformers model instance."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("Loading SentenceTransformer model '%s'...", self.model_name)
                self._model = SentenceTransformer(self.model_name)
                # Verify dimension
                test_vec = self._model.encode("test", convert_to_numpy=True)
                self._dimension = len(test_vec)
                logger.info("Model '%s' loaded successfully (dimension: %d).", self.model_name, self._dimension)
            except Exception as err:
                logger.error("Failed to load SentenceTransformer model '%s': %s", self.model_name, err)
                raise EmbeddingError(f"Could not load SentenceTransformer model '{self.model_name}': {err}") from err
        return self._model

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for a list of document chunks."""
        if not texts:
            return []

        # Validate and clean inputs
        cleaned_texts = [t.strip() if isinstance(t, str) else "" for t in texts]
        non_empty = [t if t else "empty" for t in cleaned_texts]

        try:
            model = self._load_model()
            embeddings = model.encode(
                non_empty,
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return [vec.tolist() for vec in embeddings]
        except Exception as err:
            logger.error("Batch embedding generation failed: %s", err)
            raise EmbeddingError(f"Batch embedding failed: {err}") from err

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding vector for a single search query."""
        if not text or not isinstance(text, str) or not text.strip():
            logger.warning("Empty query passed to embed_query; returning zero vector.")
            return [0.0] * self._dimension

        try:
            model = self._load_model()
            vec = model.encode(
                text.strip(),
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            return vec.tolist()
        except Exception as err:
            logger.error("Query embedding failed for '%s': %s", text[:30], err)
            raise EmbeddingError(f"Query embedding failed: {err}") from err

    def get_dimension(self) -> int:
        return self._dimension


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, lightweight embedding provider for offline testing and fallback."""

    def __init__(self, dimension: int = EMBEDDING_DIMENSION):
        self._dimension = dimension

    def _generate_vector(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self._dimension

        raw_hash = hashlib.sha256(text.strip().lower().encode("utf-8")).digest()
        # Create repeatable floats from hash bytes
        values = []
        for i in range(self._dimension):
            byte_val = raw_hash[i % len(raw_hash)]
            # Pseudo-random float between -1.0 and 1.0
            val = ((byte_val ^ (i * 31 % 256)) / 128.0) - 1.0
            values.append(val)

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        if not texts:
            return []
        return [self._generate_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._generate_vector(text)

    def get_dimension(self) -> int:
        return self._dimension


# Global singleton instance cache
_EMBEDDING_PROVIDER: Optional[BaseEmbeddingProvider] = None


def get_embedding_provider(
    force_mock: bool = False,
    model_name: str = DEFAULT_MODEL_NAME,
) -> BaseEmbeddingProvider:
    """Get or create the global embedding provider singleton.

    If force_mock is True, or if the environment variable KUBECOACH_MOCK_EMBEDDINGS=1
    is set, returns a MockEmbeddingProvider. Otherwise returns a SentenceTransformerEmbedder.
    """
    global _EMBEDDING_PROVIDER

    use_mock = force_mock or os.getenv("KUBECOACH_MOCK_EMBEDDINGS", "").strip().lower() in ("1", "true", "yes")

    if _EMBEDDING_PROVIDER is not None:
        if use_mock and isinstance(_EMBEDDING_PROVIDER, MockEmbeddingProvider):
            return _EMBEDDING_PROVIDER
        if not use_mock and isinstance(_EMBEDDING_PROVIDER, SentenceTransformerEmbedder):
            return _EMBEDDING_PROVIDER

    if use_mock:
        logger.info("Using MockEmbeddingProvider for deterministic offline embeddings.")
        _EMBEDDING_PROVIDER = MockEmbeddingProvider(dimension=EMBEDDING_DIMENSION)
    else:
        try:
            logger.info("Initializing SentenceTransformerEmbedder with model '%s'...", model_name)
            _EMBEDDING_PROVIDER = SentenceTransformerEmbedder(model_name=model_name)
        except Exception as err:
            logger.warning("Could not initialize SentenceTransformerEmbedder: %s. Falling back to Mock.", err)
            _EMBEDDING_PROVIDER = MockEmbeddingProvider(dimension=EMBEDDING_DIMENSION)

    return _EMBEDDING_PROVIDER


def embed_texts(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """Convenience helper to embed a list of texts using the default provider."""
    provider = get_embedding_provider()
    return provider.embed_texts(texts, batch_size=batch_size)


def embed_query(query: str) -> List[float]:
    """Convenience helper to embed a query using the default provider."""
    provider = get_embedding_provider()
    return provider.embed_query(query)
