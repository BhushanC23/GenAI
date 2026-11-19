"""
ui/relationships.py - Signature Feature: Kubernetes Object Relationship Strip (Day 10)

Identifies verified Kubernetes objects mentioned in an assistant's answer and retrieved
context, maps them to official Kubernetes architectural relationships, highlights the
mentioned objects, and renders a clean, responsive developer-tool relationship strip.

Never invents relationships and never renders on out-of-scope / refusal responses.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Verified Official Kubernetes Object Catalog (Tooltips & Categories)
# ---------------------------------------------------------------------------

K8S_OBJECTS: Dict[str, Dict[str, Any]] = {
    "Deployment": {
        "display": "Deployment",
        "category": "Workload",
        "tooltip": "Declaratively manages ReplicaSets and rolling updates for stateless Pods.",
        "patterns": [r"\bdeployments?\b"],
    },
    "ReplicaSet": {
        "display": "ReplicaSet",
        "category": "Workload",
        "tooltip": "Maintains a stable set of identical replica Pods running at any given time.",
        "patterns": [r"\breplicasets?\b"],
    },
    "Pods": {
        "display": "Pods",
        "category": "Workload",
        "tooltip": "Smallest deployable compute unit in Kubernetes wrapping one or more containers.",
        "patterns": [r"\bpods?\b"],
    },
    "Service": {
        "display": "Service",
        "category": "Networking",
        "tooltip": "Provides a stable ClusterIP/DNS endpoint and load balancing for a set of Pods.",
        "patterns": [r"\bservices?\b", r"\bclusterip\b", r"\bnodeport\b", r"\bloadbalancer\b"],
    },
    "Ingress": {
        "display": "Ingress",
        "category": "Networking",
        "tooltip": "Exposes HTTP and HTTPS routes from outside the cluster to internal Services.",
        "patterns": [r"\bingress(?:es)?\b"],
    },
    "StatefulSet": {
        "display": "StatefulSet",
        "category": "Workload",
        "tooltip": "Manages stateful Pods with stable network identities and persistent storage.",
        "patterns": [r"\bstatefulsets?\b"],
    },
    "DaemonSet": {
        "display": "DaemonSet",
        "category": "Workload",
        "tooltip": "Ensures a copy of a Pod runs on every (or selected) worker node in the cluster.",
        "patterns": [r"\bdaemonsets?\b"],
    },
    "Job": {
        "display": "Job",
        "category": "Workload",
        "tooltip": "Creates one or more Pods and ensures a specified number run to completion.",
        "patterns": [r"\bjobs?\b"],
    },
    "CronJob": {
        "display": "CronJob",
        "category": "Workload",
        "tooltip": "Creates Jobs on a repeating cron schedule.",
        "patterns": [r"\bcronjobs?\b"],
    },
    "ConfigMap": {
        "display": "ConfigMap",
        "category": "Configuration",
        "tooltip": "Stores non-confidential configuration key-value pairs injected into Pods.",
        "patterns": [r"\bconfigmaps?\b"],
    },
    "Secret": {
        "display": "Secret",
        "category": "Configuration",
        "tooltip": "Stores sensitive data such as passwords, tokens, and keys injected into Pods.",
        "patterns": [r"\bsecrets?\b"],
    },
    "PersistentVolumeClaim": {
        "display": "PersistentVolumeClaim",
        "category": "Storage",
        "tooltip": "A storage request by a user/Pod that binds to a matching PersistentVolume.",
        "patterns": [r"\bpersistentvolumeclaims?\b", r"\bpvcs?\b"],
    },
    "PersistentVolume": {
        "display": "PersistentVolume",
        "category": "Storage",
        "tooltip": "Cluster-provisioned storage resource independent of individual Pod lifecycles.",
        "patterns": [r"\bpersistentvolumes?\b", r"\bpvs?\b"],
    },
    "Namespace": {
        "display": "Namespace",
        "category": "Cluster",
        "tooltip": "Isolates groups of Kubernetes resources logically within a single cluster.",
        "patterns": [r"\bnamespaces?\b"],
    },
    "ResourceQuota": {
        "display": "ResourceQuota",
        "category": "Cluster",
        "tooltip": "Limits aggregate CPU, memory, and object consumption within a Namespace.",
        "patterns": [r"\bresourcequotas?\b"],
    },
    "ServiceAccount": {
        "display": "ServiceAccount",
        "category": "Security",
        "tooltip": "Provides an identity for processes running inside a Pod.",
        "patterns": [r"\bserviceaccounts?\b"],
    },
    "RoleBinding": {
        "display": "RoleBinding",
        "category": "Security",
        "tooltip": "Grants the permissions defined in a Role to a user or ServiceAccount.",
        "patterns": [r"\brolebindings?\b"],
    },
    "Role": {
        "display": "Role",
        "category": "Security",
        "tooltip": "Defines namespace-scoped RBAC permissions over Kubernetes API resources.",
        "patterns": [r"\broles?\b", r"\brbac\b"],
    },
}

# Refusal phrases indicating insufficient context (never display strip on refusals)
_REFUSAL_MARKERS = (
    "i don't know based on the provided official kubernetes documentation",
    "do not contain sufficient information to answer",
    "not part of core kubernetes",
    "was rejected by the user",
)

# Controlled official Kubernetes relationship strip definitions:
# Each entry is: (strip_title, sequence_of_(object_key_or_arrow))
# Arrows are either "→" (manages / routes to / injects into / binds to) or "←" (routes/injects into left node)
_VERIFIED_STRIPS: List[Tuple[str, Set[str], List[str]]] = [
    # 1. Combined Deployment + Service + Ingress
    (
        "Workload & Traffic Routing",
        {"Deployment", "Service", "Ingress"},
        ["Deployment", "→", "ReplicaSet", "→", "Pods", "←", "Service", "←", "Ingress"],
    ),
    # 2. Signature Deployment + ReplicaSet + Pods + Service
    (
        "Workload & Service Discovery",
        {"Deployment", "Service"},
        ["Deployment", "→", "ReplicaSet", "→", "Pods", "←", "Service"],
    ),
    # 3. Ingress -> Service -> Pods
    (
        "External HTTP/HTTPS Routing",
        {"Ingress"},
        ["Ingress", "→", "Service", "→", "Pods"],
    ),
    # 4. StatefulSet + Storage
    (
        "Stateful Workload & Storage",
        {"StatefulSet", "PersistentVolumeClaim"},
        ["StatefulSet", "→", "Pods", "→", "PersistentVolumeClaim", "→", "PersistentVolume"],
    ),
    (
        "Stateful Workload & Storage",
        {"StatefulSet", "PersistentVolume"},
        ["StatefulSet", "→", "Pods", "→", "PersistentVolumeClaim", "→", "PersistentVolume"],
    ),
    # 5. ConfigMap + Secret -> Pod
    (
        "Pod Configuration & Secrets",
        {"ConfigMap", "Secret"},
        ["ConfigMap", "→", "Pods", "←", "Secret"],
    ),
    # 6. Storage: Pod -> PVC -> PV or PVC -> PV
    (
        "Persistent Storage Binding",
        {"PersistentVolumeClaim", "Pods"},
        ["Pods", "→", "PersistentVolumeClaim", "→", "PersistentVolume"],
    ),
    (
        "Persistent Storage Binding",
        {"PersistentVolumeClaim"},
        ["PersistentVolumeClaim", "→", "PersistentVolume"],
    ),
    (
        "Persistent Storage Binding",
        {"PersistentVolume"},
        ["PersistentVolumeClaim", "→", "PersistentVolume"],
    ),
    # 7. RBAC: ServiceAccount -> RoleBinding -> Role
    (
        "RBAC Access Control",
        {"RoleBinding"},
        ["ServiceAccount", "→", "RoleBinding", "→", "Role"],
    ),
    (
        "RBAC Access Control",
        {"ServiceAccount", "Role"},
        ["ServiceAccount", "→", "RoleBinding", "→", "Role"],
    ),
    (
        "RBAC Access Control",
        {"Role"},
        ["ServiceAccount", "→", "RoleBinding", "→", "Role"],
    ),
    (
        "RBAC Access Control",
        {"ServiceAccount"},
        ["ServiceAccount", "→", "RoleBinding", "→", "Role"],
    ),
    # 8. Namespace + ResourceQuota
    (
        "Namespace Isolation & Quotas",
        {"ResourceQuota"},
        ["Namespace", "→", "ResourceQuota"],
    ),
    # 9. Core Workload Controllers
    (
        "Stateless Workload Hierarchy",
        {"Deployment"},
        ["Deployment", "→", "ReplicaSet", "→", "Pods"],
    ),
    (
        "Replica Management",
        {"ReplicaSet"},
        ["Deployment", "→", "ReplicaSet", "→", "Pods"],
    ),
    (
        "Stateful Workload",
        {"StatefulSet"},
        ["StatefulSet", "→", "Pods"],
    ),
    (
        "Node-Level Daemon Workload",
        {"DaemonSet"},
        ["DaemonSet", "→", "Pods"],
    ),
    (
        "Scheduled Batch Workload",
        {"CronJob"},
        ["CronJob", "→", "Job", "→", "Pods"],
    ),
    (
        "Batch Workload",
        {"Job"},
        ["Job", "→", "Pods"],
    ),
    # 10. Configuration singletons
    (
        "Pod Configuration Injection",
        {"ConfigMap"},
        ["ConfigMap", "→", "Pods"],
    ),
    (
        "Pod Secret Injection",
        {"Secret"},
        ["Secret", "→", "Pods"],
    ),
    # 11. Networking Service -> Pods
    (
        "Service Networking",
        {"Service"},
        ["Service", "→", "Pods"],
    ),
    # 12. Namespace isolation (when Namespace is the primary concept)
    (
        "Cluster Multi-Tenancy",
        {"Namespace"},
        ["Namespace", "→", "ResourceQuota"],
    ),
    # 13. Pod standalone (only when no more specific controller/resource matched)
    (
        "Core Pod Workload Context",
        {"Pods"},
        ["Deployment", "→", "ReplicaSet", "→", "Pods"],
    ),
]


def detect_mentioned_objects(
    question: str = "",
    answer: str = "",
    citations: Optional[List[Dict[str, Any]]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
) -> Set[str]:
    """Identify verified Kubernetes objects explicitly referenced in answer, question, and citations."""
    combined_parts: List[str] = [question or "", answer or ""]

    for citation in citations or []:
        if isinstance(citation, dict):
            combined_parts.append(str(citation.get("document_title", "")))
            combined_parts.append(str(citation.get("page", "")))

    # Only scan top chunk titles (not massive unrelated raw text) to avoid false positives
    for chunk in (retrieved_chunks or [])[:2]:
        if isinstance(chunk, dict):
            combined_parts.append(str(chunk.get("title", "")))

    corpus = " ".join(combined_parts)
    if not corpus.strip():
        return set()

    # Special guard: avoid false positive for "Service" when phrase is strictly "service mesh" or "service account"
    cleaned_corpus = re.sub(r"\bservice\s+mesh\b", " ", corpus, flags=re.IGNORECASE)
    cleaned_corpus = re.sub(r"\bservice\s+accounts?\b", " ServiceAccount ", cleaned_corpus, flags=re.IGNORECASE)

    found: Set[str] = set()
    for obj_key, meta in K8S_OBJECTS.items():
        for pattern in meta["patterns"]:
            if re.search(pattern, cleaned_corpus, flags=re.IGNORECASE):
                found.add(obj_key)
                break

    return found


def extract_object_relationships(
    question: str = "",
    answer: str = "",
    citations: Optional[List[Dict[str, Any]]] = None,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    context_sufficient: bool = True,
) -> Optional[Dict[str, Any]]:
    """Build a verified Kubernetes Object Relationship Strip for a grounded response.

    Returns None when context is insufficient, the answer is a refusal, or no
    verified Kubernetes objects are detected.
    """
    if not context_sufficient:
        return None

    lower_answer = (answer or "").lower()
    if any(marker in lower_answer for marker in _REFUSAL_MARKERS):
        return None

    mentioned = detect_mentioned_objects(
        question=question,
        answer=answer,
        citations=citations,
        retrieved_chunks=retrieved_chunks,
    )
    if not mentioned:
        return None

    # Select the highest-priority verified strip whose trigger set is a subset of mentioned objects
    selected_title: Optional[str] = None
    selected_sequence: Optional[List[str]] = None

    for title, required_objects, sequence in _VERIFIED_STRIPS:
        if required_objects.issubset(mentioned):
            selected_title = title
            selected_sequence = sequence
            break

    if not selected_sequence:
        return None

    elements: List[Dict[str, Any]] = []
    highlighted_names: List[str] = []

    for token in selected_sequence:
        if token in ("→", "←"):
            elements.append({"type": "arrow", "symbol": token})
        else:
            meta = K8S_OBJECTS[token]
            is_highlighted = token in mentioned
            # Display singular "Pod" for ConfigMap/Secret single-pod relations if preferred,
            # while keeping canonical label consistent with official Kubernetes docs.
            display_label = meta["display"]
            if token == "Pods" and ("ConfigMap" in selected_sequence or "Secret" in selected_sequence):
                display_label = "Pod"

            if is_highlighted:
                highlighted_names.append(display_label)

            elements.append({
                "type": "node",
                "key": token,
                "label": display_label,
                "category": meta["category"],
                "tooltip": meta["tooltip"],
                "highlighted": is_highlighted,
            })

    plain_text = " ".join(
        el["symbol"] if el["type"] == "arrow" else el["label"] for el in elements
    )

    return {
        "title": selected_title,
        "elements": elements,
        "mentioned_objects": sorted(mentioned),
        "highlighted_labels": highlighted_names,
        "plain_text": plain_text,
    }


def render_relationship_strip_html(strip_data: Dict[str, Any]) -> str:
    """Render a clean, accessible, responsive dark-theme HTML strip for Streamlit."""
    if not strip_data or not strip_data.get("elements"):
        return ""

    title = html.escape(str(strip_data.get("title", "Kubernetes Object Relationships")))
    chips_html: List[str] = []
    legend_items: List[str] = []

    for el in strip_data["elements"]:
        if el["type"] == "arrow":
            symbol = html.escape(el["symbol"])
            chips_html.append(
                f'<span class="kc-rel-arrow" aria-hidden="true">{symbol}</span>'
            )
        else:
            label = html.escape(el["label"])
            tooltip = html.escape(el["tooltip"])
            category = html.escape(el["category"])
            cls = "kc-rel-node kc-rel-node-active" if el["highlighted"] else "kc-rel-node"
            chips_html.append(
                f'<span class="{cls}" title="{label} ({category}): {tooltip}">'
                f'<span class="kc-rel-node-label">{label}</span>'
                f"</span>"
            )
            if el["highlighted"]:
                legend_items.append(
                    f'<span class="kc-rel-legend-item"><strong>{label}:</strong> {tooltip}</span>'
                )

    nodes_markup = "".join(chips_html)
    legend_markup = "".join(legend_items[:3])

    return (
        '<div class="kc-rel-container">'
        f'  <div class="kc-rel-header">KUBERNETES OBJECT RELATIONSHIPS &middot; {title}</div>'
        f'  <div class="kc-rel-strip">{nodes_markup}</div>'
        f'  <div class="kc-rel-legend">{legend_markup}</div>'
        "</div>"
    )
