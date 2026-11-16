"""Unit tests for KubeCoach Day 7: Document Chunking, Embeddings, ChromaDB, and Semantic Search."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Enable mock embeddings for ultra-fast, deterministic unit test execution
os.environ["KUBECOACH_MOCK_EMBEDDINGS"] = "1"

from fastapi.testclient import TestClient

from app.chunking import (
    TextChunk,
    clean_markdown_for_chunking,
    chunk_document,
    chunk_record,
    load_and_chunk_all_documents,
    split_text,
)
from app.embed import (
    EMBEDDING_DIMENSION,
    MockEmbeddingProvider,
    embed_query,
    embed_texts,
    get_embedding_provider,
)
from app.main import app
from app.vectorstore import KubeCoachVectorStore, get_vector_store


class TestChunking(unittest.TestCase):
    """Test suite for document and record chunking functionality."""

    def test_clean_markdown_for_chunking(self) -> None:
        raw_text = (
            "<!-- overview -->\n"
            'A Pod is {{< glossary_tooltip text="container" term_id="container" >}} workload.\n'
            "{{< caution >}}Keep secrets secure.{{< /caution >}}\n"
            "Visit [Kubernetes Docs](https://kubernetes.io) for more."
        )
        cleaned = clean_markdown_for_chunking(raw_text)
        self.assertNotIn("<!-- overview -->", cleaned)
        self.assertNotIn("glossary_tooltip", cleaned)
        self.assertIn("container", cleaned)
        self.assertIn("Kubernetes Docs (https://kubernetes.io)", cleaned)

    def test_split_text_with_overlap(self) -> None:
        sample_doc = (
            "Kubernetes is an open source container orchestration engine. "
            "It automates deployment, scaling, and management of containerized applications. "
            "A Pod is the smallest execution unit in Kubernetes. "
            "Deployments manage Pod replicas declaratively. "
            "Services expose Pods to network traffic."
        )
        chunks = split_text(sample_doc, chunk_size=120, chunk_overlap=30)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 150)  # Allowance for natural boundary expansion
            self.assertGreater(len(chunk), 15)

    def test_chunk_document_metadata_preservation(self) -> None:
        content = "A Service in Kubernetes is an abstraction which defines a logical set of Pods and access policy."
        metadata = {
            "source": "raw/service.md",
            "page": "service",
            "title": "Services",
            "category": "networking",
        }
        chunks = chunk_document(content, metadata, chunk_size=100, chunk_overlap=20)
        self.assertEqual(len(chunks), 1)
        first_chunk = chunks[0]
        self.assertTrue(first_chunk.id.startswith("service-c001-"))
        self.assertEqual(first_chunk.metadata["source"], "raw/service.md")
        self.assertEqual(first_chunk.metadata["page"], "service")
        self.assertEqual(first_chunk.metadata["title"], "Services")
        self.assertEqual(first_chunk.metadata["category"], "networking")

    def test_chunk_record(self) -> None:
        record = {
            "id": "deployment",
            "page_title": "Deployments",
            "category": "workload",
            "one_line_definition": "A controller that declaratively manages Pods and ReplicaSets.",
            "key_kubectl_command": "kubectl create deployment nginx --image=nginx",
            "limit_or_default": "The default rolling update allows 25% max unavailable.",
            "source_url": "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
        }
        chunks = chunk_record(record)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertIn("Deployments", chunks[0].text)
        self.assertIn("kubectl create deployment", chunks[0].text)
        self.assertEqual(chunks[0].metadata["page"], "deployment")
        self.assertEqual(chunks[0].metadata["category"], "workload")

    def test_empty_and_invalid_inputs(self) -> None:
        self.assertEqual(split_text(""), [])
        self.assertEqual(split_text("   "), [])
        self.assertEqual(chunk_document("", {}), [])
        self.assertEqual(chunk_record({}), [])

    def test_load_and_chunk_all_documents(self) -> None:
        chunks = load_and_chunk_all_documents()
        self.assertGreater(len(chunks), 50)
        # Verify metadata consistency
        for chunk in chunks[:10]:
            self.assertIn("source", chunk.metadata)
            self.assertIn("page", chunk.metadata)
            self.assertIn("title", chunk.metadata)
            self.assertTrue(chunk.id)
            self.assertTrue(chunk.text)


class TestEmbeddings(unittest.TestCase):
    """Test suite for vector embeddings generation."""

    def test_mock_provider_deterministic_and_normalized(self) -> None:
        provider = MockEmbeddingProvider(dimension=EMBEDDING_DIMENSION)
        vec1 = provider.embed_query("What is a Pod?")
        vec2 = provider.embed_query("What is a Pod?")
        self.assertEqual(len(vec1), EMBEDDING_DIMENSION)
        self.assertEqual(vec1, vec2)  # Deterministic repeatability

        # Test L2 norm ~ 1.0
        norm = sum(x * x for x in vec1) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=4)

    def test_batch_embedding(self) -> None:
        texts = ["Pod", "Deployment", "Service", "ConfigMap"]
        embeddings = embed_texts(texts, batch_size=2)
        self.assertEqual(len(embeddings), 4)
        for vec in embeddings:
            self.assertEqual(len(vec), EMBEDDING_DIMENSION)

    def test_empty_query_embedding(self) -> None:
        provider = get_embedding_provider(force_mock=True)
        zero_vec = provider.embed_query("")
        self.assertEqual(len(zero_vec), EMBEDDING_DIMENSION)
        self.assertEqual(sum(zero_vec), 0.0)


class TestVectorStore(unittest.TestCase):
    """Test suite for persistent ChromaDB storage and similarity search."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.mkdtemp(prefix="kubecoach_test_chroma_")
        cls.store = KubeCoachVectorStore(
            persist_dir=Path(cls.temp_dir),
            collection_name="test_collection",
        )
        cls.store.get_collection()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_add_chunks_and_deduplication(self) -> None:
        chunks = [
            TextChunk(
                id="doc1-c001",
                text="A Pod is the smallest deployable compute unit in Kubernetes.",
                metadata={"source": "test", "page": "pod", "title": "Pod", "category": "workload"},
            ),
            TextChunk(
                id="doc2-c001",
                text="A Service routes external network traffic to internal Pods.",
                metadata={"source": "test", "page": "service", "title": "Service", "category": "networking"},
            ),
        ]
        count1 = self.store.add_chunks(chunks)
        self.assertEqual(count1, 2)
        self.assertEqual(self.store.count(), 2)

        # Upserting identical chunks again must not create duplicates
        count2 = self.store.add_chunks(chunks)
        self.assertEqual(count2, 2)
        self.assertEqual(self.store.count(), 2)

    def test_query_similar_with_category_filter(self) -> None:
        chunks = [
            TextChunk(
                id="workload-pod",
                text="Pods run containerized processes across worker nodes.",
                metadata={"source": "test", "page": "pod", "title": "Pod", "category": "workload"},
            ),
            TextChunk(
                id="network-service",
                text="Services configure IP addresses and load balancers.",
                metadata={"source": "test", "page": "service", "title": "Service", "category": "networking"},
            ),
        ]
        self.store.add_chunks(chunks)

        # Search with networking category filter
        results = self.store.query_similar("network load balancer", n_results=2, category="networking")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["category"], "networking")
        self.assertEqual(results[0]["page"], "service")

    def test_empty_query_returns_empty_list(self) -> None:
        self.assertEqual(self.store.query_similar(""), [])
        self.assertEqual(self.store.query_similar("   "), [])


class TestSemanticSearchAPI(unittest.TestCase):
    """Test suite for FastAPI semantic search endpoint."""

    @classmethod
    def setUpClass(cls) -> None:
        store = get_vector_store()
        store.get_collection()

    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_semantic_search_success(self) -> None:
        resp = self.client.get("/search/semantic?q=pod+container+execution&limit=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["query"], "pod container execution")
        self.assertIn("results", data)
        self.assertLessEqual(len(data["results"]), 2)
        if data["results"]:
            first = data["results"][0]
            self.assertIn("chunk_id", first)
            self.assertIn("text", first)
            self.assertIn("similarity", first)
            self.assertIn("distance", first)
            self.assertIn("source", first)
            self.assertIn("title", first)

    def test_semantic_search_empty_query_returns_422(self) -> None:
        resp = self.client.get("/search/semantic?q=")
        self.assertEqual(resp.status_code, 422)

    def test_root_endpoint_includes_semantic_search(self) -> None:
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("semantic_search_url", data)

    def test_preserved_previous_endpoints(self) -> None:
        # Verify Day 4 /health
        h_resp = self.client.get("/health")
        self.assertEqual(h_resp.status_code, 200)

        # Verify Day 4 /records
        r_resp = self.client.get("/records?limit=2")
        self.assertEqual(r_resp.status_code, 200)

        # Verify Day 4 /search (TF-IDF)
        s_resp = self.client.get("/search?q=deployment")
        self.assertEqual(s_resp.status_code, 200)

        # Verify Day 6 /chat
        c_resp = self.client.post("/chat", json={"question": "What is a Pod?"})
        self.assertEqual(c_resp.status_code, 200)
        self.assertIn("answer", c_resp.json())


if __name__ == "__main__":
    unittest.main()
