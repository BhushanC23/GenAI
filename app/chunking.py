"""Document chunking module for KubeCoach.

Provides functionality to split Kubernetes documentation and knowledge records
into smaller text chunks with configurable chunk size and overlap, while
preserving critical metadata (source, page, title, category) and generating
deterministic, unique chunk IDs.
"""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("kubecoach.chunking")

DEFAULT_CHUNK_SIZE = 500  # Target character size per chunk
DEFAULT_CHUNK_OVERLAP = 100  # Character overlap between adjacent chunks


@dataclass
class TextChunk:
    """Represents a discrete chunk of text extracted from a document."""

    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to a dictionary representation."""
        return asdict(self)


def clean_markdown_for_chunking(text: str) -> str:
    """Clean Hugo shortcodes, HTML comments, and extra whitespace from markdown text."""
    if not text:
        return ""

    # Replace Hugo glossary tooltips with display text or term_id
    text = re.sub(r'\{\{<\s*glossary_tooltip[^>]*text="([^"]+)"[^>]*>\}\}', r"\1", text)
    text = re.sub(r'\{\{<\s*glossary_tooltip[^>]*term_id="([^"]+)"[^>]*>\}\}', r"\1", text)
    # Strip any remaining Hugo shortcodes: {{< ... >}}
    text = re.sub(r"\{\{<.*?>\}\}", "", text)
    # Remove HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Remove markdown link markup [text](url) -> text (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    # Normalize multiple whitespace characters while keeping paragraph breaks
    paragraphs = [re.sub(r"[ \t]+", " ", p).strip() for p in text.split("\n\n")]
    paragraphs = [p for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def split_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks using paragraph, sentence, and word boundaries.

    Args:
        text: Raw or pre-cleaned text to split.
        chunk_size: Maximum desired character length per chunk (must be > 0).
        chunk_overlap: Number of characters to overlap between consecutive chunks.

    Returns:
        A list of non-empty text chunk strings.
    """
    if not text or not isinstance(text, str):
        return []

    text = text.strip()
    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be non-negative.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be strictly less than chunk_size.")

    # If the text is already smaller than or equal to the desired chunk size, return it directly.
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    start = 0
    text_len = len(text)
    step = chunk_size - chunk_overlap

    while start < text_len:
        end = min(start + chunk_size, text_len)

        # If not at the very end of text, find a natural boundary near the end
        if end < text_len:
            # Look backwards from 'end' for a paragraph break, newline, sentence terminator, or space
            slice_zone = text[max(start, end - 100):end]

            # Try paragraph break first
            p_break = slice_zone.rfind("\n\n")
            if p_break != -1:
                end = max(start, end - 100) + p_break + 2
            else:
                # Try sentence end (. ! ?)
                sent_match = None
                for match in re.finditer(r"[\.!\?]\s+", slice_zone):
                    sent_match = match
                if sent_match:
                    end = max(start, end - 100) + sent_match.end()
                else:
                    # Fallback to newline
                    nl_break = slice_zone.rfind("\n")
                    if nl_break != -1:
                        end = max(start, end - 100) + nl_break + 1
                    else:
                        # Fallback to space
                        sp_break = slice_zone.rfind(" ")
                        if sp_break != -1:
                            end = max(start, end - 100) + sp_break + 1

        chunk_candidate = text[start:end].strip()
        if chunk_candidate and len(chunk_candidate) > 15:
            # Avoid inserting duplicate chunks
            if not chunks or chunks[-1] != chunk_candidate:
                chunks.append(chunk_candidate)

        # Advance start index
        next_start = start + step
        if next_start <= start:
            next_start = start + 1
        start = next_start

    return chunks


def generate_chunk_id(page: str, index: int, text: str) -> str:
    """Generate a stable, unique chunk identifier using page slug and content hash prefix."""
    safe_page = re.sub(r"[^a-zA-Z0-9_\-]", "-", page).strip("-").lower() or "chunk"
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"{safe_page}-c{index:03d}-{content_hash}"


def chunk_document(
    content: str,
    metadata: Dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[TextChunk]:
    """Process a raw document string into a list of TextChunk objects with preserved metadata.

    Args:
        content: The text content of the document.
        metadata: Metadata dictionary containing at least 'source', 'page', and 'title'.
        chunk_size: Max characters per chunk.
        chunk_overlap: Overlapping characters between adjacent chunks.

    Returns:
        List of TextChunk instances.
    """
    if not content or not isinstance(content, str):
        return []

    # Clean markdown formatting and shortcodes
    cleaned = clean_markdown_for_chunking(content)
    if not cleaned:
        return []

    raw_chunks = split_text(cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    page = str(metadata.get("page", metadata.get("id", "doc")))
    title = str(metadata.get("title", metadata.get("page_title", page)))
    source = str(metadata.get("source", metadata.get("source_url", "local")))

    result_chunks: List[TextChunk] = []
    for idx, piece in enumerate(raw_chunks, start=1):
        chunk_id = generate_chunk_id(page, idx, piece)
        chunk_meta = dict(metadata)
        chunk_meta.update(
            {
                "source": source,
                "page": page,
                "title": title,
                "chunk_index": idx,
                "total_chunks_in_doc": len(raw_chunks),
                "char_length": len(piece),
            }
        )
        result_chunks.append(TextChunk(id=chunk_id, text=piece, metadata=chunk_meta))

    return result_chunks


def chunk_record(
    record: Dict[str, Any],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[TextChunk]:
    """Chunk a structured KubeCoach knowledge base record into semantic TextChunks."""
    if not record or not isinstance(record, dict):
        return []

    rec_id = str(record.get("id", "record"))
    title = str(record.get("page_title", rec_id.title()))
    category = str(record.get("category", "general"))
    definition = str(record.get("one_line_definition", ""))
    command = str(record.get("key_kubectl_command", ""))
    limits = str(record.get("limit_or_default", ""))
    source = str(record.get("source_url", f"https://kubernetes.io/docs/concepts/{category}/{rec_id}/"))

    formatted_content = (
        f"Kubernetes Concept: {title} ({rec_id})\n"
        f"Category: {category}\n"
        f"Definition: {definition}\n"
        f"Key kubectl Command: {command}\n"
        f"Limits and Defaults: {limits}"
    )

    meta = {
        "source": source,
        "source_url": source,
        "page": rec_id,
        "title": title,
        "category": category,
        "record_id": rec_id,
    }

    return chunk_document(
        content=formatted_content,
        metadata=meta,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def load_and_chunk_all_documents(
    raw_dir: Optional[Path] = None,
    records_json_path: Optional[Path] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[TextChunk]:
    """Load both raw official documentation files and structured records and chunk them.

    Args:
        raw_dir: Path to directory containing raw markdown files (defaults to data/raw/).
        records_json_path: Path to records.json file (defaults to data/records.json).
        chunk_size: Desired chunk character length.
        chunk_overlap: Desired chunk overlap.

    Returns:
        Combined list of all TextChunk objects with preserved metadata.
    """
    repo_root = Path(__file__).resolve().parent.parent
    if raw_dir is None:
        raw_dir = repo_root / "data" / "raw"
    if records_json_path is None:
        records_json_path = repo_root / "data" / "records.json"

    all_chunks: List[TextChunk] = []
    seen_ids = set()

    # 1. Chunk structured records from records.json (primary 18 official concepts)
    if records_json_path.exists():
        try:
            with open(records_json_path, "r", encoding="utf-8") as f:
                records_data = json.load(f)
            for rec in records_data:
                rec_chunks = chunk_record(rec, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                for chunk in rec_chunks:
                    if chunk.id not in seen_ids:
                        seen_ids.add(chunk.id)
                        all_chunks.append(chunk)
            logger.info("Chunked %d records from %s into %d chunks.", len(records_data), records_json_path.name, len(all_chunks))
        except Exception as err:
            logger.error("Failed to load records from %s: %s", records_json_path, err)

    # 2. Chunk raw official markdown files in data/raw
    if raw_dir.exists() and raw_dir.is_dir():
        # Load manifest if available for official source URLs and categories
        manifest_map: Dict[str, Dict[str, Any]] = {}
        manifest_file = raw_dir / "manifest.json"
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as mf:
                    manifest_list = json.load(mf)
                for item in manifest_list:
                    if isinstance(item, dict) and "filename" in item:
                        manifest_map[item["filename"]] = item
            except Exception as m_err:
                logger.warning("Could not read manifest.json: %s", m_err)

        md_files = list(raw_dir.glob("*.md"))
        for md_path in md_files:
            try:
                content = md_path.read_text(encoding="utf-8")
                slug = md_path.stem.lower()

                manifest_entry = manifest_map.get(md_path.name, {})
                source_url = manifest_entry.get(
                    "source_url", f"https://kubernetes.io/docs/concepts/{slug}/"
                )
                category = manifest_entry.get("category", "general")

                # Derive clean title from frontmatter, manifest or filename
                title = manifest_entry.get("title")
                if not title:
                    title = slug.replace("-", " ").title()
                    for line in content.splitlines()[:15]:
                        if line.startswith("title:"):
                            title = line.replace("title:", "").strip().strip('"\'')
                            break

                meta = {
                    "source": f"raw/{md_path.name}",
                    "source_url": source_url,
                    "page": md_path.name,
                    "title": title,
                    "category": category,
                    "file_path": str(md_path),
                }

                doc_chunks = chunk_document(
                    content=content,
                    metadata=meta,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                for chunk in doc_chunks:
                    if chunk.id not in seen_ids:
                        seen_ids.add(chunk.id)
                        all_chunks.append(chunk)

                logger.info("Chunked raw doc '%s' into %d chunks.", md_path.name, len(doc_chunks))
            except Exception as err:
                logger.error("Failed to chunk raw file %s: %s", md_path, err)

    logger.info("Total chunks generated across all documents: %d", len(all_chunks))
    return all_chunks
