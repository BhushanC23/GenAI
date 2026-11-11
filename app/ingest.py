"""Data ingestion pipeline for KubeCoach.

Reads raw official documentation files from data/raw/, parses and normalizes
the content (handling Markdown, frontmatter, and Hugo shortcodes), validates
records using the Record dataclass, handles invalid or malformed rows gracefully
with logging, and saves cleaned records to data/records.json.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.models import DataIngestionError, Record, ValidationError
from data.sample_records import SAMPLE_RECORDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kubecoach.ingest")


def get_paths() -> Tuple[Path, Path, Path]:
    """Return (data_dir, raw_dir, output_json_path)."""
    base_data = Path(__file__).resolve().parent.parent / "data"
    raw_dir = base_data / "raw"
    output_json = base_data / "records.json"
    return base_data, raw_dir, output_json


def clean_doc_text(text: str) -> str:
    """Normalize documentation text by stripping Hugo shortcodes, HTML, and Markdown."""
    # Handle Hugo glossary tooltips with text attribute: {{< glossary_tooltip text="Pods" ... >}} -> Pods
    text = re.sub(r'\{\{<\s*glossary_tooltip[^>]*text="([^"]+)"[^>]*>\}\}', r"\1", text)
    # Handle Hugo glossary tooltips with term_id attribute: {{< glossary_tooltip term_id="controller" >}} -> controller
    text = re.sub(r'\{\{<\s*glossary_tooltip[^>]*term_id="([^"]+)"[^>]*>\}\}', r"\1", text)
    # Strip any remaining Hugo shortcodes: {{< ... >}}
    text = re.sub(r"\{\{<.*?>\}\}", "", text)
    # Remove HTML comments like <!-- overview -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    # Remove markdown links [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown emphasis markers (* and _)
    text = re.sub(r"[_*`]", "", text)
    # Collapse multiple whitespaces and newlines
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_frontmatter_and_overview(content: str) -> Dict[str, str]:
    """Extract top-level metadata and overview paragraph from official Kubernetes doc Markdown."""
    metadata: Dict[str, str] = {}
    lines = content.splitlines()

    # Parse YAML frontmatter (only top-level unindented keys)
    in_frontmatter = False
    body_start_idx = 0
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                body_start_idx = idx + 1
                break
        elif in_frontmatter and ":" in stripped:
            # Only consider top-level keys (not indented nested attributes like feature.title)
            if not line.startswith(" ") and not line.startswith("\t"):
                key, val = stripped.split(":", 1)
                clean_key = key.strip().lower()
                clean_val = val.strip().strip('"\'')
                if clean_key not in metadata:
                    metadata[clean_key] = clean_val

    # Look for overview section
    body_text = "\n".join(lines[body_start_idx:])
    overview_match = re.search(
        r"<!--\s*overview\s*-->(.*?)(?:<!--|\n##|\Z)",
        body_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if overview_match:
        raw_overview = overview_match.group(1).strip()
    else:
        # Fall back to first non-empty paragraph
        paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
        raw_overview = paragraphs[0] if paragraphs else ""

    metadata["overview"] = clean_doc_text(raw_overview)
    return metadata


def build_knowledge_records(
    raw_dir: Optional[Path] = None,
) -> Tuple[List[Record], List[str]]:
    """Ingest raw documentation and seed records, returning (valid_records, errors).

    Ensures invalid records are caught and logged without aborting ingestion.
    """
    _, default_raw_dir, _ = get_paths()
    target_raw_dir = raw_dir or default_raw_dir

    valid_records: List[Record] = []
    errors: List[str] = []

    # Map seed records by ID for fast lookup
    seed_by_id: Dict[str, Dict[str, str]] = {
        rec["id"].lower(): rec for rec in SAMPLE_RECORDS
    }

    # Load manifest if available
    manifest_map: Dict[str, Dict[str, Any]] = {}
    manifest_file = target_raw_dir / "manifest.json"
    if manifest_file.exists():
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            for entry in manifest_data:
                if entry.get("status") == "success":
                    manifest_map[entry["filename"]] = entry
        except Exception as exc:
            logger.warning("Could not parse manifest.json: %s", exc)

    # Ingest from raw files if directory exists
    if target_raw_dir.exists():
        for md_file in sorted(target_raw_dir.glob("*.md")):
            try:
                raw_text = md_file.read_text(encoding="utf-8")
                parsed = parse_frontmatter_and_overview(raw_text)
                manifest_entry = manifest_map.get(md_file.name, {})

                file_id = manifest_entry.get("id") or md_file.stem.lower()
                seed = seed_by_id.get(file_id)

                page_title = (seed["page_title"] if seed else parsed.get("title")) or md_file.stem.title()
                category = manifest_entry.get("category") or (seed["category"] if seed else "general")
                one_line_definition = seed["one_line_definition"] if seed else parsed.get("overview", "")
                key_kubectl_command = seed["key_kubectl_command"] if seed else f"kubectl get {file_id}"
                limit_or_default = seed["limit_or_default"] if seed else "See official documentation for defaults."
                source_url = manifest_entry.get("source_url") or (seed["source_url"] if seed else "https://kubernetes.io/docs/concepts/")

                record_data = {
                    "id": file_id,
                    "page_title": page_title,
                    "category": category,
                    "one_line_definition": one_line_definition,
                    "key_kubectl_command": key_kubectl_command,
                    "limit_or_default": limit_or_default,
                    "source_url": source_url,
                }

                # Validate using Record dataclass
                rec = Record.from_dict(record_data)
                valid_records.append(rec)
                logger.info("Ingested raw doc '%s' -> Record(id='%s')", md_file.name, rec.id)
            except ValidationError as v_err:
                msg = f"Validation failed for {md_file.name}: {v_err}"
                logger.warning(msg)
                errors.append(msg)
            except Exception as exc:
                msg = f"Error processing file {md_file.name}: {exc}"
                logger.error(msg)
                errors.append(msg)

    # Add any remaining seed records not already added from raw files
    ingested_ids = {r.id.lower() for r in valid_records}
    for rec_id, seed_data in seed_by_id.items():
        if rec_id not in ingested_ids:
            try:
                rec = Record.from_dict(seed_data)
                valid_records.append(rec)
                logger.info("Ingested verified record -> Record(id='%s')", rec.id)
            except ValidationError as v_err:
                msg = f"Validation failed for seed record '{rec_id}': {v_err}"
                logger.warning(msg)
                errors.append(msg)

    # Sort deterministically by id
    valid_records.sort(key=lambda r: r.id)
    return valid_records, errors


def save_records_to_json(
    records: List[Record],
    output_path: Optional[Path] = None,
) -> Path:
    """Save cleaned and validated records to JSON file."""
    _, _, default_out = get_paths()
    target_path = output_path or default_out
    target_path.parent.mkdir(parents=True, exist_ok=True)

    records_dicts = [r.to_dict() for r in records]
    target_path.write_text(json.dumps(records_dicts, indent=2), encoding="utf-8")
    logger.info("Saved %d records to %s", len(records), target_path)
    return target_path


def run_ingestion() -> Tuple[int, int]:
    """Execute the full data-ingestion pipeline.

    Returns (valid_record_count, error_count).
    """
    logger.info("Starting KubeCoach data ingestion pipeline...")
    valid_records, errors = build_knowledge_records()
    if not valid_records:
        raise DataIngestionError("No valid records were generated by the pipeline.")

    save_records_to_json(valid_records)
    logger.info(
        "Ingestion complete: %d valid records, %d warnings/errors.",
        len(valid_records),
        len(errors),
    )
    return len(valid_records), len(errors)


def main() -> None:
    """CLI entrypoint for running the ingestion pipeline."""
    print("=" * 60)
    print("KubeCoach — Documentation Ingestion Pipeline")
    print("=" * 60)
    valid_count, err_count = run_ingestion()
    _, _, out_path = get_paths()
    print(f"\nSuccessfully created: {out_path}")
    print(f"Total valid records: {valid_count}")
    print(f"Warnings/errors: {err_count}")


if __name__ == "__main__":
    main()
