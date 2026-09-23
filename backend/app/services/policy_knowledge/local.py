"""LocalPolicyKnowledgeService: keyword/section retrieval over extracted policy text
and the structured PostgreSQL rows (coverages, conditions). Used when Cognee is
unavailable. Same interface, so the agents never know which backend answered."""
import re
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.models import Policy
from app.services.policy_knowledge.base import KnowledgeChunk, PolicyContext, PolicyKnowledgeService

_STOP = {"is", "my", "the", "a", "an", "do", "i", "have", "what", "covered", "cover", "does", "for", "of", "in", "to", "and", "are", "me", "policy", "under", "this", "it", "can", "will", "be"}

SYNONYMS: Dict[str, List[str]] = {
    "icu": ["icu", "intensive care", "critical care"],
    "room": ["room rent", "room", "boarding"],
    "dental": ["dental", "teeth", "tooth"],
    "maternity": ["maternity", "pregnancy", "delivery", "newborn"],
    "waiting": ["waiting period", "waiting"],
    "expire": ["expiry", "expires", "policy period", "valid till", "end date"],
    "ambulance": ["ambulance"],
    "cashless": ["cashless", "network hospital"],
    "reimbursement": ["reimbursement"],
    "deductible": ["deductible", "co-pay", "copay", "co-payment"],
    "pre-existing": ["pre-existing", "pre existing", "ped"],
    "daycare": ["day care", "daycare"],
    "cataract": ["cataract"],
    "cosmetic": ["cosmetic", "plastic surgery"],
    "theft": ["theft", "stolen", "burglary"],
    "third": ["third party", "third-party", "tp"],
    "depreciation": ["depreciation", "zero dep", "zero depreciation"],
    "engine": ["engine protect", "engine"],
    "documents": ["documents", "document", "required", "checklist"],
    "claim": ["claim process", "claim procedure", "how to claim", "intimation"],
}


def _tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9\-]+", text.lower()) if t not in _STOP and len(t) > 1]


def _expand(tokens: List[str]) -> List[str]:
    out = list(tokens)
    for t in tokens:
        for key, syns in SYNONYMS.items():
            if t.startswith(key[:4]) or t in syns:
                out.extend(syns)
    return list(dict.fromkeys(out))


def split_sections(text: str) -> List[Dict[str, str]]:
    """Split policy text into titled sections using ALL-CAPS or numbered headers."""
    lines = text.splitlines()
    sections: List[Dict[str, str]] = []
    current_title = "General"
    buffer: List[str] = []
    header_re = re.compile(r"^(\d+(\.\d+)*\.?\s+[A-Z][^\n]{2,80}|[A-Z][A-Z \-/&()]{4,80})$")
    for line in lines:
        stripped = line.strip()
        if header_re.match(stripped) and len(stripped) < 90:
            if buffer:
                sections.append({"title": current_title, "text": "\n".join(buffer).strip()})
            current_title = stripped
            buffer = []
        else:
            buffer.append(line)
    if buffer:
        sections.append({"title": current_title, "text": "\n".join(buffer).strip()})
    # Chunk long sections into ~600-char windows
    chunks: List[Dict[str, str]] = []
    for s in sections:
        body = s["text"]
        if not body:
            continue
        for i in range(0, len(body), 600):
            chunks.append({"title": s["title"], "text": body[i : i + 700]})
    return chunks


class LocalPolicyKnowledgeService(PolicyKnowledgeService):
    name = "local"

    def __init__(self, db: Session):
        self.db = db

    def ingest_policy(self, policy_id: str, text: str, structured_profile: Dict[str, Any]) -> bool:
        # Text and structured rows are already persisted in PostgreSQL by PolicyService.
        return True

    def _policy(self, policy_id: str) -> Policy:
        policy = self.db.get(Policy, policy_id)
        if not policy:
            raise KeyError(policy_id)
        return policy

    def search_policy(self, policy_id: str, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        policy = self._policy(policy_id)
        terms = _expand(_tokens(query))
        results: List[KnowledgeChunk] = []

        for cov in policy.coverages:
            hay = " ".join([cov.name, " ".join(cov.keywords or []), cov.condition_text, cov.limit_text]).lower()
            score = sum(2.0 if t in hay else 0 for t in terms)
            if score:
                text = f"{cov.name}: covered={cov.covered}" + (f"; limit {cov.limit_text}" if cov.limit_text else "") + (f"; condition: {cov.condition_text}" if cov.condition_text else "")
                results.append(KnowledgeChunk(text=text, source=cov.section_ref or "Coverage schedule", score=score + 1, kind="coverage"))
        for cond in policy.conditions:
            hay = " ".join([cond.kind, cond.title, cond.description, cond.value]).lower()
            score = sum(1.5 if t in hay else 0 for t in terms)
            if score:
                text = f"[{cond.kind.replace('_', ' ').title()}] {cond.title}" + (f" — {cond.value}" if cond.value else "") + (f". {cond.description}" if cond.description else "")
                results.append(KnowledgeChunk(text=text, source=cond.section_ref or cond.kind, score=score + 0.5, kind="condition"))
        for chunk in split_sections(policy.extracted_text or ""):
            hay = (chunk["title"] + " " + chunk["text"]).lower()
            score = sum(1.0 if t in hay else 0 for t in terms)
            if score:
                results.append(KnowledgeChunk(text=chunk["text"][:600], source=chunk["title"], score=score, kind="text"))

        results.sort(key=lambda c: c.score, reverse=True)
        return results[:top_k]

    def get_related_requirements(self, policy_id: str, topic: str) -> List[str]:
        policy = self._policy(policy_id)
        reqs = [c.title for c in policy.conditions if c.kind == "REQUIRED_DOCUMENT"]
        if not reqs:
            reqs = list((policy.structured_profile or {}).get("required_documents", []))
        return reqs

    def get_policy_context(self, policy_id: str, query: str) -> PolicyContext:
        chunks = self.search_policy(policy_id, query, top_k=6)
        policy = self._policy(policy_id)
        summary = {
            "policy_type": policy.policy_type,
            "sum_insured": policy.sum_insured,
            "waiting_period_days": policy.waiting_period_days,
            "deductible": policy.deductible,
            "end_date": policy.end_date.date().isoformat() if policy.end_date else None,
            "coverage_count": len(policy.coverages),
            "exclusion_count": len([c for c in policy.conditions if c.kind == "EXCLUSION"]),
        }
        return PolicyContext(policy_id=policy_id, backend=self.name, chunks=chunks, related_requirements=self.get_related_requirements(policy_id, query), graph_summary=summary)

    def status(self) -> Dict[str, Any]:
        return {"backend": self.name, "configured": True, "note": "PostgreSQL + section search fallback"}
