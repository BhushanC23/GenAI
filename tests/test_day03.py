"""Automated tests for Day 3 KubeCoach implementations.

Verifies:
1. Record dataclass instantiation and schema validation
2. Custom error handling for invalid/missing fields
3. HTTP fetcher resilience on network and status errors
4. Ingestion pipeline and JSON serialization
5. Loading cleaned records and dataclass models
6. Compatibility with existing search, count, and lookup functions
"""

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from app.fetch import DEFAULT_TIMEOUT_SECONDS, fetch_official_documents, fetch_url
from app.ingest import (
    build_knowledge_records,
    clean_doc_text,
    parse_frontmatter_and_overview,
    run_ingestion,
)
from app.models import (
    DataIngestionError,
    KubeCoachError,
    Record,
    ValidationError,
)
from app.records import (
    count_by,
    get_by_id,
    load_record_models,
    load_records,
    search,
)


class TestRecordModel(unittest.TestCase):
    """Test Record dataclass behavior and validation."""

    def test_valid_record_creation(self) -> None:
        rec = Record(
            id="pod",
            page_title="Pods",
            category="workload",
            one_line_definition="Smallest deployable unit.",
            key_kubectl_command="kubectl get pods",
            limit_or_default="Configurable.",
            source_url="https://kubernetes.io/docs/concepts/workloads/pods/",
        )
        self.assertEqual(rec.id, "pod")
        self.assertEqual(rec.page_title, "Pods")
        d = rec.to_dict()
        self.assertEqual(d["id"], "pod")
        self.assertEqual(d["category"], "workload")

    def test_slugify_when_id_empty(self) -> None:
        rec = Record(
            page_title="Network Policies",
            category="networking",
            one_line_definition="Specifications of how pods communicate.",
            key_kubectl_command="kubectl get netpol",
            limit_or_default="Disabled by default.",
            source_url="https://kubernetes.io/docs/concepts/services-networking/network-policies/",
        )
        self.assertEqual(rec.id, "network-policies")

    def test_missing_required_field_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            Record(
                page_title="",
                category="workload",
                one_line_definition="A definition",
                key_kubectl_command="cmd",
                limit_or_default="limit",
                source_url="https://kubernetes.io/docs/",
            )

    def test_invalid_url_raises_validation_error(self) -> None:
        with self.assertRaises(ValidationError):
            Record(
                page_title="Invalid URL Concept",
                category="workload",
                one_line_definition="A definition",
                key_kubectl_command="cmd",
                limit_or_default="limit",
                source_url="ftp://kubernetes.io/docs/",
            )

    def test_from_dict_and_to_dict_roundtrip(self) -> None:
        data = {
            "id": "service",
            "page_title": "Service",
            "category": "networking",
            "one_line_definition": "Exposes Pods over the network.",
            "key_kubectl_command": "kubectl get svc",
            "limit_or_default": "ClusterIP default",
            "source_url": "https://kubernetes.io/docs/concepts/services-networking/service/",
        }
        rec = Record.from_dict(data)
        self.assertEqual(rec.to_dict(), data)


class TestFetcher(unittest.TestCase):
    """Test HTTP fetching logic and error handling."""

    @patch("requests.get")
    def test_fetch_url_success(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.text = "# Sample Kubernetes Docs"
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = fetch_url("https://kubernetes.io/test", timeout=DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual(result, "# Sample Kubernetes Docs")
        mock_resp.raise_for_status.assert_called_once()
        mock_resp.close.assert_called_once()

    @patch("requests.get")
    def test_fetch_url_timeout_handled(self, mock_get: MagicMock) -> None:
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")
        with self.assertRaises(requests.exceptions.Timeout):
            fetch_url("https://kubernetes.io/slow-page")

    @patch("requests.get")
    def test_fetch_url_http_error_handled(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_resp

        with self.assertRaises(requests.exceptions.HTTPError):
            fetch_url("https://kubernetes.io/not-found")


class TestIngestion(unittest.TestCase):
    """Test data normalization, parsing, and JSON ingestion."""

    def test_clean_doc_text(self) -> None:
        raw = '{{< glossary_tooltip text="Pods" term_id="pod" >}} are **small** _units_ <!-- overview -->'
        cleaned = clean_doc_text(raw)
        self.assertEqual(cleaned, "Pods are small units")

    def test_parse_frontmatter_and_overview(self) -> None:
        doc = """---
title: Deployments
weight: 10
feature:
  title: Nested Feature
---
<!-- overview -->
A Deployment provides declarative updates for Pods.
"""
        parsed = parse_frontmatter_and_overview(doc)
        self.assertEqual(parsed.get("title"), "Deployments")
        self.assertEqual(parsed.get("overview"), "A Deployment provides declarative updates for Pods.")

    def test_run_ingestion_generates_json(self) -> None:
        valid_count, errors = run_ingestion()
        self.assertGreaterEqual(valid_count, 18)
        self.assertEqual(errors, 0)

        json_path = Path(__file__).resolve().parent.parent / "data" / "records.json"
        self.assertTrue(json_path.exists())
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 18)


class TestRecordLoadingAndQueries(unittest.TestCase):
    """Verify records.py loads the JSON and satisfies Day 2 query functions."""

    def test_load_records_reads_json(self) -> None:
        records = load_records()
        self.assertGreaterEqual(len(records), 18)
        first = records[0]
        self.assertIn("id", first)
        self.assertIn("page_title", first)
        self.assertIn("category", first)

    def test_load_record_models(self) -> None:
        models = load_record_models()
        self.assertGreaterEqual(len(models), 18)
        self.assertIsInstance(models[0], Record)

    def test_search_functionality(self) -> None:
        records = load_records()
        pod_results = search(records, "pod")
        self.assertGreater(len(pod_results), 0)
        self.assertEqual(search(records, "   "), [])

    def test_count_by_category(self) -> None:
        records = load_records()
        counts = count_by(records, "category")
        self.assertIn("workload", counts)
        self.assertGreater(counts["workload"], 0)

    def test_get_by_id(self) -> None:
        records = load_records()
        rec = get_by_id(records, "pod")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], "pod")
        self.assertEqual(rec["page_title"], "Pods")


if __name__ == "__main__":
    unittest.main()
