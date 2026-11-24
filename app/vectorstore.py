"""Persistent ChromaDB vector storage module for KubeCoach.

Provides management of a local, disk-backed ChromaDB vector collection for
indexing Kubernetes documentation chunks, generating dense embeddings, and
executing semantic similarity queries with metadata filtering.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Disable ChromaDB telemetry globally to avoid network hangs and external tracking
os.environ["ANONYMIZED_TELEMETRY"] = "False"
try:
    import posthog
    posthog.disabled = True
except ImportError:
    pass

from app.chunking import TextChunk, load_and_chunk_all_documents
from app.embed import embed_query, embed_texts, get_embedding_provider

logger = logging.getLogger("kubecoach.vectorstore")

DEFAULT_COLLECTION_NAME = "kubecoach_docs"
DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma_db"


class VectorStoreError(Exception):
    """Raised when vector storage or retrieval operations fail."""


class KubeCoachVectorStore:
    """Manages persistent ChromaDB vector storage and semantic search for KubeCoach."""

    def __init__(
        self,
        persist_dir: Optional[Path] = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
    ):
        self.persist_dir = Path(persist_dir) if persist_dir else DEFAULT_DB_DIR
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _get_client(self):
        """Lazy initialize persistent ChromaDB client."""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings

                self.persist_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Initializing ChromaDB PersistentClient at '%s'...", self.persist_dir)
                self._client = chromadb.PersistentClient(
                    path=str(self.persist_dir),
                    settings=Settings(anonymized_telemetry=False, allow_reset=True),
                )
            except Exception as err:
                logger.error("Failed to initialize ChromaDB PersistentClient: %s", err)
                raise VectorStoreError(f"Could not initialize ChromaDB client: {err}") from err
        return self._client

    def get_collection(self):
        """Get or create the ChromaDB collection."""
        if self._collection is None:
            client = self._get_client()
            try:
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=None,
                    metadata={
                        "description": "KubeCoach official Kubernetes documentation and records",
                        "hnsw:space": "cosine",
                        "hnsw:sync_threshold": 50,
                    },
                )
                current_cnt = self._collection.count()
                logger.info(
                    "Accessed ChromaDB collection '%s' (current count: %d).",
                    self.collection_name,
                    current_cnt,
                )
            except Exception as err:
                logger.error("Failed to access ChromaDB collection '%s': %s", self.collection_name, err)
                raise VectorStoreError(f"Could not get or create collection '{self.collection_name}': {err}") from err
        return self._collection

    def count(self) -> int:
        """Return the number of items stored in the collection."""
        try:
            return self.get_collection().count()
        except Exception as err:
            logger.error("Failed to count items in vector store: %s", err)
            return 0

    def add_chunks(self, chunks: List[TextChunk], batch_size: int = 64) -> int:
        """Add or update chunks in the persistent vector store using upsert.

        Args:
            chunks: List of TextChunk instances to store.
            batch_size: Batch size for embedding and upserting.

        Returns:
            Number of chunks indexed.
        """
        if not chunks:
            logger.info("No chunks provided to index.")
            return 0

        collection = self.get_collection()
        total_indexed = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i : i + batch_size]
            ids = [c.id for c in batch]
            documents = [c.text for c in batch]

            # Clean and stringify metadata values to conform to ChromaDB constraints (no nested dicts/None)
            metadatas = []
            for c in batch:
                clean_meta: Dict[str, Any] = {}
                for k, v in c.metadata.items():
                    if v is None:
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        clean_meta[k] = v
                    else:
                        clean_meta[k] = str(v)
                metadatas.append(clean_meta)

            try:
                # Compute embeddings in batch
                embeddings = embed_texts(documents, batch_size=batch_size)

                # Upsert to ChromaDB to safely avoid duplicates
                collection.upsert(
                    ids=ids,
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                total_indexed += len(batch)
                logger.info("Indexed batch %d-%d (%d chunks).", i + 1, i + len(batch), total_indexed)
            except Exception as err:
                logger.error("Failed to upsert batch into ChromaDB: %s", err)
                raise VectorStoreError(f"Failed to index chunk batch: {err}") from err

        logger.info("Successfully indexed %d chunks into collection '%s'.", total_indexed, self.collection_name)
        return total_indexed

    def index_documents(
        self,
        force_reindex: bool = False,
        raw_dir: Optional[Path] = None,
        records_json_path: Optional[Path] = None,
    ) -> int:
        """Index all raw documents and knowledge records into the vector collection.

        If force_reindex is False and the collection already holds exactly the chunks the current
        chunking code produces, returns the current count. If the stored chunk IDs differ (for
        example the index was built by an older version of the chunker, so its metadata or text is
        out of date), the stale chunks are deleted and every current chunk is upserted again.
        """
        collection = self.get_collection()
        current_count = collection.count()

        logger.info(
            "Preparing document index for collection '%s' (existing=%d, force_reindex=%s)...",
            self.collection_name,
            current_count,
            force_reindex,
        )
        chunks = load_and_chunk_all_documents(raw_dir=raw_dir, records_json_path=records_json_path)

        if current_count > 0 and not force_reindex:
            return self.sync_chunks(chunks)
        return self.add_chunks(chunks)

    def sync_chunks(self, chunks: List[TextChunk]) -> int:
        """Make the collection match `chunks` exactly, re-embedding only when it is out of date.

        Chunk IDs contain a hash of the chunk text, so if the stored IDs equal the expected IDs the
        index is current and nothing is embedded. Otherwise stale IDs are deleted and every expected
        chunk is upserted again (this also refreshes metadata such as `source_url`).

        Returns:
            Number of chunks stored in the collection after synchronisation.
        """
        collection = self.get_collection()
        expected_ids = {c.id for c in chunks}
        stored_ids = set(collection.get(include=[])["ids"])

        if stored_ids == expected_ids:
            logger.info(
                "Vector collection '%s' already contains %d up-to-date chunks. Skipping reindex.",
                self.collection_name,
                len(stored_ids),
            )
            return len(stored_ids)

        stale_ids = sorted(stored_ids - expected_ids)
        logger.warning(
            "Vector collection '%s' is out of date (%d stale, %d missing chunks). Rebuilding index...",
            self.collection_name,
            len(stale_ids),
            len(expected_ids - stored_ids),
        )
        for i in range(0, len(stale_ids), 500):
            collection.delete(ids=stale_ids[i : i + 500])
        return self.add_chunks(chunks)

    def query_similar(
        self,
        query_text: str,
        n_results: int = 3,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform semantic search against the persistent ChromaDB collection.

        Args:
            query_text: User search query.
            n_results: Maximum number of chunks to return (default 3).
            category: Optional category filter (e.g. 'workload', 'networking').
            source: Optional source filter.

        Returns:
            List of result dictionaries containing text, distance, similarity, source, page, title, and metadata.
        """
        if not query_text or not isinstance(query_text, str) or not query_text.strip():
            logger.info("Empty search query provided to query_similar; returning empty results.")
            return []

        clean_query = query_text.strip()
        collection = self.get_collection()
        total_available = collection.count()

        if total_available == 0:
            logger.warning("Vector store is empty. Please run index_documents() first.")
            return []

        limit = min(max(1, n_results), total_available)

        # Build where filter if specified
        where_filter: Optional[Dict[str, Any]] = None
        filters: List[Dict[str, Any]] = []
        if category and isinstance(category, str) and category.strip():
            filters.append({"category": category.strip().lower()})
        if source and isinstance(source, str) and source.strip():
            filters.append({"source": source.strip()})

        if len(filters) == 1:
            where_filter = filters[0]
        elif len(filters) > 1:
            where_filter = {"$and": filters}

        try:
            # Generate query embedding
            query_vector = embed_query(clean_query)

            # Query ChromaDB
            results = collection.query(
                query_embeddings=[query_vector],
                n_results=limit,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            formatted_results: List[Dict[str, Any]] = []
            doc_list = results.get("documents", [[]])[0]
            meta_list = results.get("metadatas", [[]])[0]
            dist_list = results.get("distances", [[]])[0]
            id_list = results.get("ids", [[]])[0]

            for idx, doc_text in enumerate(doc_list):
                meta = meta_list[idx] if idx < len(meta_list) else {}
                dist = float(dist_list[idx]) if idx < len(dist_list) else 0.0
                chunk_id = id_list[idx] if idx < len(id_list) else ""

                # Normalized similarity score between 0.0 and 1.0
                similarity = round(max(0.0, min(1.0, 1.0 - (dist / 2.0))), 4)

                formatted_results.append(
                    {
                        "chunk_id": chunk_id,
                        "text": doc_text,
                        "distance": round(dist, 4),
                        "similarity": similarity,
                        "source": meta.get("source", "unknown"),
                        "source_url": meta.get(
                            "source_url", meta.get("source", "https://kubernetes.io/docs/concepts/")
                        ),
                        "page": meta.get("page", "unknown"),
                        "title": meta.get("title", meta.get("page", "unknown")),
                        "category": meta.get("category", "general"),
                        "metadata": meta,
                    }
                )

            logger.info("Semantic query '%s' returned %d results.", clean_query, len(formatted_results))
            return formatted_results

        except Exception as err:
            logger.error("Failed to execute semantic query for '%s': %s", clean_query, err)
            raise VectorStoreError(f"Semantic search failed: {err}") from err


# Module-level default singleton instance
_VECTOR_STORE: Optional[KubeCoachVectorStore] = None


def get_vector_store(
    persist_dir: Optional[Path] = None,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> KubeCoachVectorStore:
    """Get or create the singleton KubeCoachVectorStore instance."""
    global _VECTOR_STORE
    if _VECTOR_STORE is None or persist_dir is not None:
        _VECTOR_STORE = KubeCoachVectorStore(
            persist_dir=persist_dir,
            collection_name=collection_name,
        )
    return _VECTOR_STORE


def query_semantic(
    query_text: str,
    n_results: int = 3,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convenience helper to query the default persistent vector store."""
    store = get_vector_store()
    return store.query_similar(query_text=query_text, n_results=n_results, category=category)
