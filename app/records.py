"""Functions for loading and querying the Kubernetes records dataset.

Supports loading cleaned records from data/records.json with fallback
to data/sample_records.py, and provides querying, filtering, and counting.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.models import Record as RecordModel
from data.sample_records import SAMPLE_RECORDS

# Type alias matching Day 2 dictionary records
RecordDict = Dict[str, str]

DATA_FILE_PATH = Path(__file__).resolve().parent.parent / "data" / "records.json"


def load_records(path: Optional[Union[str, Path]] = None) -> List[RecordDict]:
    """Load Kubernetes records as dictionaries from records.json.

    Falls back to SAMPLE_RECORDS if the JSON file is missing or unreadable.
    """
    target_path = Path(path) if path else DATA_FILE_PATH

    if target_path.is_file():
        try:
            content = target_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass

    # Safe fallback to preserve Day 2 behavior
    return [record.copy() for record in SAMPLE_RECORDS]


def load_record_models(path: Optional[Union[str, Path]] = None) -> List[RecordModel]:
    """Load Kubernetes records as validated Record dataclass objects."""
    raw_records = load_records(path)
    return [RecordModel.from_dict(rec) for rec in raw_records]


def search(records: List[Any], keyword: str) -> List[Any]:
    """Return records containing keyword in any text field.

    Compatible with both dictionary records and Record dataclass objects.
    An empty or whitespace-only keyword returns an empty list.
    """
    normalized_keyword = keyword.strip().lower()
    if not normalized_keyword:
        return []

    results = []
    for record in records:
        if isinstance(record, dict):
            haystack = " ".join(str(v) for v in record.values()).lower()
        elif hasattr(record, "to_dict"):
            haystack = " ".join(str(v) for v in record.to_dict().values()).lower()
        else:
            haystack = " ".join(str(getattr(record, f)) for f in getattr(record, "__annotations__", {})).lower()

        if normalized_keyword in haystack:
            results.append(record)

    return results


def count_by(records: List[Any], field: str) -> Dict[str, int]:
    """Count records grouped by a field, skipping records without that field."""
    keys: List[str] = []
    for record in records:
        if isinstance(record, dict):
            if field in record:
                keys.append(str(record[field]))
        elif hasattr(record, field):
            keys.append(str(getattr(record, field)))
    return dict(Counter(keys))


def get_by_id(records: List[Any], record_id: str) -> Optional[Any]:
    """Return one record by ID, or None when the ID is not found."""
    normalized_id = record_id.strip().lower()
    for record in records:
        if isinstance(record, dict):
            if str(record.get("id", "")).lower() == normalized_id:
                return record
        elif hasattr(record, "id"):
            if str(getattr(record, "id", "")).lower() == normalized_id:
                return record
    return None
