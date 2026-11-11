"""Data models and custom exceptions for KubeCoach.

Defines the standard Record dataclass used across ingestion,
storage, and query modules.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


class KubeCoachError(Exception):
    """Base exception for all KubeCoach custom errors."""


class ValidationError(KubeCoachError):
    """Raised when a record fails schema validation."""


class DataIngestionError(KubeCoachError):
    """Raised when data ingestion or parsing fails."""


@dataclass
class Record:
    """Represents one structured Kubernetes knowledge record.

    Matches the standard KubeCoach 6-field format with a unique identifier.
    """

    page_title: str
    category: str
    one_line_definition: str
    key_kubectl_command: str
    limit_or_default: str
    source_url: str
    id: str = ""

    def __post_init__(self) -> None:
        """Validate fields and assign a fallback ID if missing."""
        self.validate()
        if not self.id:
            self.id = self._slugify(self.page_title)

    @staticmethod
    def _slugify(text: str) -> str:
        """Generate a URL-friendly slug from title text."""
        cleaned = "".join(c.lower() if c.isalnum() else "-" for c in text.strip())
        parts = [p for p in cleaned.split("-") if p]
        return "-".join(parts) if parts else "record"

    def validate(self) -> None:
        """Validate and normalize record field values."""
        self.page_title = str(self.page_title).strip()
        self.category = str(self.category).strip().lower()
        self.one_line_definition = str(self.one_line_definition).strip()
        self.key_kubectl_command = str(self.key_kubectl_command).strip()
        self.limit_or_default = str(self.limit_or_default).strip()
        self.source_url = str(self.source_url).strip()
        self.id = str(self.id).strip().lower()

        if not self.page_title:
            raise ValidationError("Field 'page_title' cannot be empty.")
        if not self.category:
            raise ValidationError("Field 'category' cannot be empty.")
        if not self.one_line_definition:
            raise ValidationError("Field 'one_line_definition' cannot be empty.")
        if not self.source_url:
            raise ValidationError("Field 'source_url' cannot be empty.")
        if not (self.source_url.startswith("http://") or self.source_url.startswith("https://")):
            raise ValidationError(
                f"Field 'source_url' must be a valid HTTP(S) URL, got: {self.source_url}"
            )

    def to_dict(self) -> Dict[str, str]:
        """Convert the Record instance to a standard dictionary."""
        return {
            "id": self.id,
            "page_title": self.page_title,
            "category": self.category,
            "one_line_definition": self.one_line_definition,
            "key_kubectl_command": self.key_kubectl_command,
            "limit_or_default": self.limit_or_default,
            "source_url": self.source_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Record":
        """Construct and validate a Record instance from a dictionary."""
        if not isinstance(data, dict):
            raise ValidationError(
                f"Record data must be a dictionary, got {type(data).__name__}"
            )

        required_keys = ("page_title", "category", "one_line_definition")
        for key in required_keys:
            if key not in data or not str(data[key]).strip():
                raise ValidationError(f"Missing or empty required field: '{key}'")

        return cls(
            id=str(data.get("id", "")).strip(),
            page_title=str(data.get("page_title", "")).strip(),
            category=str(data.get("category", "")).strip(),
            one_line_definition=str(data.get("one_line_definition", "")).strip(),
            key_kubectl_command=str(data.get("key_kubectl_command", "")).strip(),
            limit_or_default=str(data.get("limit_or_default", "")).strip(),
            source_url=str(data.get("source_url", "")).strip(),
        )
