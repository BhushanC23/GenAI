"""Official Kubernetes documentation fetcher for KubeCoach.

Downloads raw concept documentation pages from the official Kubernetes
documentation repository using HTTP GET requests with timeouts,
status validation, and error handling.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kubecoach.fetch")

# Official documentation sources from the Kubernetes website repository
OFFICIAL_DOC_SOURCES: List[Dict[str, str]] = [
    {
        "id": "pod",
        "title": "Pods",
        "category": "workload",
        "filename": "pods.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/workloads/pods/_index.md",
        "source_url": "https://kubernetes.io/docs/concepts/workloads/pods/",
    },
    {
        "id": "deployment",
        "title": "Deployments",
        "category": "workload",
        "filename": "deployment.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/workloads/controllers/deployment.md",
        "source_url": "https://kubernetes.io/docs/concepts/workloads/controllers/deployment/",
    },
    {
        "id": "service",
        "title": "Services",
        "category": "networking",
        "filename": "service.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/services-networking/service.md",
        "source_url": "https://kubernetes.io/docs/concepts/services-networking/service/",
    },
    {
        "id": "configmap",
        "title": "ConfigMaps",
        "category": "configuration",
        "filename": "configmap.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/configuration/configmap.md",
        "source_url": "https://kubernetes.io/docs/concepts/configuration/configmap/",
    },
    {
        "id": "namespace",
        "title": "Namespaces",
        "category": "cluster-management",
        "filename": "namespaces.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/overview/working-with-objects/namespaces.md",
        "source_url": "https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/",
    },
    {
        "id": "ingress",
        "title": "Ingress",
        "category": "networking",
        "filename": "ingress.md",
        "raw_url": "https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/concepts/services-networking/ingress.md",
        "source_url": "https://kubernetes.io/docs/concepts/services-networking/ingress/",
    },
]

DEFAULT_TIMEOUT_SECONDS = 15


def get_raw_dir() -> Path:
    """Return the Path to the raw data directory, creating it if needed."""
    raw_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir


def fetch_url(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Perform an HTTP GET request with timeouts and status validation.

    Demonstrates try / except / else / finally error handling.
    """
    logger.info("Fetching: %s", url)
    response = None
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "KubeCoach-Educational-Fetcher/1.0"},
        )
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        logger.error("Request timed out for %s: %s", url, exc)
        raise
    except requests.exceptions.HTTPError as exc:
        logger.error("HTTP error %s for %s: %s", response.status_code if response else "N/A", url, exc)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error("Network request failed for %s: %s", url, exc)
        raise
    else:
        logger.info("Successfully fetched %d bytes from %s", len(response.text), url)
        return response.text
    finally:
        if response is not None:
            response.close()


def fetch_official_documents(
    sources: Optional[List[Dict[str, str]]] = None,
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """Fetch official Kubernetes documentation files and save them locally.

    Returns the list of paths to successfully downloaded raw files.
    """
    doc_sources = sources or OFFICIAL_DOC_SOURCES
    target_dir = output_dir or get_raw_dir()
    downloaded_paths: List[Path] = []
    manifest: List[Dict[str, Any]] = []

    for src in doc_sources:
        filename = src["filename"]
        target_path = target_dir / filename
        url = src["raw_url"]

        try:
            content = fetch_url(url)
            # Write using standard utf-8 encoding
            target_path.write_text(content, encoding="utf-8")
            downloaded_paths.append(target_path)

            manifest.append(
                {
                    "id": src["id"],
                    "title": src["title"],
                    "category": src["category"],
                    "filename": filename,
                    "source_url": src["source_url"],
                    "raw_url": url,
                    "bytes": len(content.encode("utf-8")),
                    "fetched_at": datetime.utcnow().isoformat() + "Z",
                    "status": "success",
                }
            )
            logger.info("Saved raw file to %s", target_path)
        except Exception as exc:
            logger.warning("Failed to fetch %s (%s): %s", src["title"], url, exc)
            manifest.append(
                {
                    "id": src["id"],
                    "title": src["title"],
                    "category": src["category"],
                    "filename": filename,
                    "source_url": src["source_url"],
                    "raw_url": url,
                    "error": str(exc),
                    "status": "failed",
                }
            )

    # Save manifest.json for data provenance
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info("Wrote fetch manifest to %s", manifest_path)

    return downloaded_paths


def main() -> None:
    """CLI entrypoint for testing document fetching."""
    print("=" * 60)
    print("KubeCoach — Official Documentation Fetcher")
    print("=" * 60)
    downloaded = fetch_official_documents()
    print(f"\nSuccessfully downloaded {len(downloaded)} raw documentation files.")
    for p in downloaded:
        print(f"  - {p.name} ({p.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
