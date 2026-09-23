"""PolicyKnowledgeService interface.

Cognee is the primary knowledge layer for policy documents. The local
implementation keeps the app runnable when Cognee is not configured.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class KnowledgeChunk(BaseModel):
    text: str
    source: str = ""
    score: float = 0.0
    kind: str = "text"  # text / coverage / condition / graph


class PolicyContext(BaseModel):
    policy_id: str
    backend: str
    chunks: List[KnowledgeChunk] = Field(default_factory=list)
    related_requirements: List[str] = Field(default_factory=list)
    graph_summary: Dict[str, Any] = Field(default_factory=dict)


class PolicyKnowledgeService(ABC):
    name: str = "base"

    @abstractmethod
    def ingest_policy(self, policy_id: str, text: str, structured_profile: Dict[str, Any]) -> bool: ...

    @abstractmethod
    def search_policy(self, policy_id: str, query: str, top_k: int = 5) -> List[KnowledgeChunk]: ...

    @abstractmethod
    def get_policy_context(self, policy_id: str, query: str) -> PolicyContext: ...

    @abstractmethod
    def get_related_requirements(self, policy_id: str, topic: str) -> List[str]: ...

    def status(self) -> Dict[str, Any]:
        return {"backend": self.name}
