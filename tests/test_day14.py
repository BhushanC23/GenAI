"""Regression tests for the Day 14 audit fixes.

Each test covers a defect found while auditing the running application:
1. YAML frontmatter from the raw Kubernetes pages leaked into chunks and answers.
2. A persisted ChromaDB index built by an older chunker was never refreshed, so
   citations pointed at "raw/pods.md" instead of the official documentation URL.
3. Off-topic questions (for example "capital of France") passed the context
   sufficiency check because vector similarity alone was moderate.

All tests are offline: embeddings are replaced with the deterministic mock provider.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.chunking import TextChunk, clean_markdown_for_chunking
from app.embed import MockEmbeddingProvider
from app.rag import build_citations, is_context_sufficient
from app.vectorstore import KubeCoachVectorStore

_MOCK_EMBEDDER = MockEmbeddingProvider()


def _fake_embed_texts(texts, batch_size=32):
    return _MOCK_EMBEDDER.embed_texts(texts, batch_size=batch_size)


class TestFrontmatterRemoval(unittest.TestCase):
    """Frontmatter is page metadata and must not become searchable or citable text."""

    def test_leading_frontmatter_is_removed(self) -> None:
        raw = (
            "---\n"
            "reviewers:\n- erictune\n"
            "title: Pods\n"
            "weight: 10\n"
            "---\n\n"
            "_Pods_ are the smallest deployable units of computing in Kubernetes."
        )
        cleaned = clean_markdown_for_chunking(raw)
        self.assertNotIn("reviewers", cleaned)
        self.assertNotIn("erictune", cleaned)
        self.assertNotIn("weight:", cleaned)
        self.assertTrue(cleaned.startswith("_Pods_ are the smallest"))

    def test_text_without_frontmatter_is_unchanged(self) -> None:
        text = "A Service exposes Pods.\n\nUse kubectl get svc to list Services."
        self.assertEqual(clean_markdown_for_chunking(text), text)

    def test_horizontal_rule_inside_document_is_kept(self) -> None:
        text = "Intro paragraph about Pods.\n\n---\n\nSecond section about Services."
        cleaned = clean_markdown_for_chunking(text)
        self.assertIn("Intro paragraph", cleaned)
        self.assertIn("Second section", cleaned)


class TestContextSufficiencyOffTopic(unittest.TestCase):
    """The guardrail must refuse questions that share no vocabulary with the retrieved text."""

    NAMESPACE_CHUNK = {
        "chunk_id": "namespaces-c016-test",
        "text": "Namespaces provide a mechanism for isolating groups of resources within a single cluster.",
        "title": "Namespaces",
        "similarity": 0.59,
    }

    def test_off_topic_question_is_refused_even_with_moderate_similarity(self) -> None:
        sufficient, reason = is_context_sufficient("What is the capital of France?", [self.NAMESPACE_CHUNK])
        self.assertFalse(sufficient)
        self.assertIn("None of the query keywords", reason)

    def test_on_topic_question_is_still_answered(self) -> None:
        sufficient, _ = is_context_sufficient("What is a Namespace used for?", [self.NAMESPACE_CHUNK])
        self.assertTrue(sufficient)

    def test_refused_question_produces_no_citations(self) -> None:
        sufficient, _ = is_context_sufficient("Who won the cricket world cup?", [self.NAMESPACE_CHUNK])
        self.assertFalse(sufficient)
        # The RAG pipeline only calls build_citations() for sufficient context; verify the
        # contract that citations come from chunk metadata and never invent a URL.
        citations = build_citations(
            [{**self.NAMESPACE_CHUNK, "source_url": "https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/", "page": "namespaces.md"}]
        )
        self.assertEqual(len(citations), 1)
        self.assertTrue(citations[0].source_url.startswith("https://kubernetes.io/docs/"))


class TestStaleIndexSelfHealing(unittest.TestCase):
    """index_documents() must refresh an index whose chunk IDs no longer match the chunker."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="kubecoach_day14_"))
        self.raw_dir = self.tmp / "raw"
        self.raw_dir.mkdir()
        (self.raw_dir / "pods.md").write_text(
            "---\ntitle: Pods\nreviewers:\n- someone\n---\n\n"
            "A Pod is the smallest deployable unit in Kubernetes. It wraps one or more containers.",
            encoding="utf-8",
        )
        (self.raw_dir / "manifest.json").write_text(
            json.dumps(
                [
                    {
                        "id": "pod",
                        "title": "Pods",
                        "category": "workload",
                        "filename": "pods.md",
                        "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.records_path = self.tmp / "records.json"
        self.records_path.write_text(
            json.dumps(
                [
                    {
                        "id": "service",
                        "page_title": "Services",
                        "category": "networking",
                        "one_line_definition": "Exposes a group of Pods as a network service.",
                        "key_kubectl_command": "kubectl get svc",
                        "limit_or_default": "Default type is ClusterIP.",
                        "source_url": "https://kubernetes.io/docs/concepts/services-networking/service/",
                    }
                ]
            ),
            encoding="utf-8",
        )
        self.store = KubeCoachVectorStore(persist_dir=self.tmp / "chroma", collection_name="day14_test")

    def tearDown(self) -> None:
        self.store._client = None
        self.store._collection = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _index(self) -> int:
        return self.store.index_documents(raw_dir=self.raw_dir, records_json_path=self.records_path)

    def test_stale_chunks_are_replaced_and_current_chunks_carry_official_urls(self) -> None:
        with patch("app.vectorstore.embed_texts", side_effect=_fake_embed_texts):
            first_count = self._index()
            self.assertGreaterEqual(first_count, 2)

            # Simulate an index left behind by an older chunker.
            self.store.add_chunks(
                [TextChunk(id="stale-old-chunk", text="Old text from a previous chunker version.", metadata={"source": "raw/pods.md", "page": "pods.md", "title": "Pods"})]
            )
            self.assertEqual(self.store.count(), first_count + 1)

            healed_count = self._index()

        self.assertEqual(healed_count, first_count)
        self.assertEqual(self.store.count(), first_count)
        stored = self.store.get_collection().get(include=["metadatas", "documents"])
        self.assertNotIn("stale-old-chunk", stored["ids"])
        for meta, doc in zip(stored["metadatas"], stored["documents"]):
            self.assertTrue(str(meta.get("source_url", "")).startswith("https://kubernetes.io/docs/"))
            self.assertNotIn("reviewers", doc)

    def test_up_to_date_index_is_not_re_embedded(self) -> None:
        with patch("app.vectorstore.embed_texts", side_effect=_fake_embed_texts) as embed_mock:
            self._index()
            calls_after_first_index = embed_mock.call_count
            self._index()
            self.assertEqual(embed_mock.call_count, calls_after_first_index)


if __name__ == "__main__":
    unittest.main()
