from typing import Any, Dict

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.policy_knowledge.base import KnowledgeChunk, PolicyContext, PolicyKnowledgeService  # noqa: F401
from app.services.policy_knowledge.cognee import CogneePolicyKnowledgeService
from app.services.policy_knowledge.local import LocalPolicyKnowledgeService


def get_policy_knowledge_service(db: Session) -> PolicyKnowledgeService:
    """Cognee when enabled and importable, otherwise the local fallback."""
    settings = get_settings()
    if settings.COGNEE_ENABLED:
        svc = CogneePolicyKnowledgeService(db)
        if svc.available:
            return svc
    return LocalPolicyKnowledgeService(db)


def knowledge_status(db: Session) -> Dict[str, Any]:
    settings = get_settings()
    if settings.COGNEE_ENABLED:
        return CogneePolicyKnowledgeService(db).status()
    return {"backend": "local", "configured": False, "available": False, "note": "Set COGNEE_ENABLED=true and install requirements-cognee.txt to enable Cognee."}
