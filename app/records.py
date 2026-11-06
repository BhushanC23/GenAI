"""Functions for loading and querying the Kubernetes records dataset."""

from collections import Counter
from typing import Dict, List, Optional

from data.sample_records import SAMPLE_RECORDS

Record = Dict[str, str]


def load_records() -> List[Record]:
    """Return all Kubernetes records as a new list."""
    return [record.copy() for record in SAMPLE_RECORDS]


def search(records: List[Record], keyword: str) -> List[Record]:
    """Return records containing keyword in any text field.

    An empty or whitespace-only keyword returns an empty list.
    """
    normalized_keyword = keyword.strip().lower()
    if not normalized_keyword:
        return []

    return [
        record
        for record in records
        if normalized_keyword in " ".join(record.values()).lower()
    ]


def count_by(records: List[Record], field: str) -> Dict[str, int]:
    """Count records grouped by a field, skipping records without that field."""
    return dict(Counter(record[field] for record in records if field in record))


def get_by_id(records: List[Record], record_id: str) -> Optional[Record]:
    """Return one record by ID, or None when the ID is not found."""
    normalized_id = record_id.strip().lower()
    for record in records:
        if record.get("id", "").lower() == normalized_id:
            return record
    return None
