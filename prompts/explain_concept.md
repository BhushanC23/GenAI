# KubeCoach — Concept Explanation Prompt Template

Use this prompt template when a student asks to understand or compare Kubernetes API objects (e.g. Pods, Deployments, Services, ConfigMaps).

## Pedagogical Structure to Follow in the `answer` field:
1. **One-Line Definition:** State what the object is in plain English.
2. **The "Why":** Explain the specific problem this object solves (e.g., why a Pod alone is insufficient and needs a Deployment).
3. **Real-World Analogy:** Use a relatable analogy (e.g., Pod as a shipping container, Deployment as a factory manager, Service as a receptionist).
4. **Key `kubectl` Command:** Show how to inspect or create the object.
5. **Important Defaults / Limits:** Mention critical defaults (e.g. ClusterIP type, 25% rolling update surge, base64 Secret encoding).

## Output Requirement
Return strictly the JSON object:
```json
{
  "answer": "...",
  "confidence": "high",
  "follow_up": "..."
}
```
