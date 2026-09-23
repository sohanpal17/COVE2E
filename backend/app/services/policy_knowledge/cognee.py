"""CogneePolicyKnowledgeService: policy intelligence graph/knowledge layer.

Uses the `cognee` SDK (optional dependency, see requirements-cognee.txt). Each
policy is ingested into its own dataset so retrieval is policy-specific. Any
failure degrades to the local service so the app never breaks.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.policy_knowledge.base import KnowledgeChunk, PolicyContext, PolicyKnowledgeService
from app.services.policy_knowledge.local import LocalPolicyKnowledgeService

logger = logging.getLogger(__name__)


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():  # pragma: no cover - inside async context
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro)).result()
    return asyncio.run(coro)


class CogneePolicyKnowledgeService(PolicyKnowledgeService):
    name = "cognee"

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.fallback = LocalPolicyKnowledgeService(db)
        self._cognee = None
        self.last_error: str | None = None
        self._available = self._load()

    def _load(self) -> bool:
        if not self.settings.COGNEE_ENABLED:
            return False
        try:
            if self.settings.COGNEE_API_KEY and not os.environ.get("LLM_API_KEY"):
                # Cognee's SDK reads its LLM key from LLM_API_KEY.
                os.environ["LLM_API_KEY"] = self.settings.COGNEE_API_KEY
            import cognee  # type: ignore

            self._cognee = cognee
            return True
        except Exception as exc:
            self.last_error = f"cognee import failed: {exc}"
            logger.warning("Cognee unavailable, using local knowledge service: %s", exc)
            return False

    @property
    def available(self) -> bool:
        return self._available and self._cognee is not None

    @staticmethod
    def _dataset(policy_id: str) -> str:
        return f"cove2e_policy_{policy_id.replace('-', '_')}"

    def ingest_policy(self, policy_id: str, text: str, structured_profile: Dict[str, Any]) -> bool:
        if not self.available:
            return self.fallback.ingest_policy(policy_id, text, structured_profile)
        try:
            cognee = self._cognee
            dataset = self._dataset(policy_id)
            profile_lines = [f"{k}: {v}" for k, v in structured_profile.items() if not isinstance(v, (dict, list))]
            docs = [text, "POLICY PROFILE\n" + "\n".join(profile_lines)]
            for cov in structured_profile.get("coverages", []):
                docs.append(f"COVERAGE: {cov.get('name')} is {cov.get('covered')} covered. Limit: {cov.get('limit_text', 'none')}. Condition: {cov.get('condition_text', 'none')}.")
            for cond in structured_profile.get("conditions", []):
                docs.append(f"{cond.get('kind')}: {cond.get('title')} — {cond.get('value', '')}. {cond.get('description', '')}")

            async def _go():
                await cognee.add(docs, dataset_name=dataset)
                await cognee.cognify(datasets=[dataset])

            _run(_go())
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = f"ingest: {exc}"
            logger.warning("Cognee ingest failed for %s: %s", policy_id, exc)
            return False

    def search_policy(self, policy_id: str, query: str, top_k: int = 5) -> List[KnowledgeChunk]:
        if not self.available:
            return self.fallback.search_policy(policy_id, query, top_k)
        try:
            cognee = self._cognee
            dataset = self._dataset(policy_id)

            async def _go():
                try:
                    from cognee.modules.search.types import SearchType  # type: ignore

                    return await cognee.search(query_text=query, query_type=SearchType.GRAPH_COMPLETION, datasets=[dataset])
                except Exception:
                    return await cognee.search(query_text=query, datasets=[dataset])

            results = _run(_go()) or []
            chunks: List[KnowledgeChunk] = []
            for r in results[:top_k]:
                text = r if isinstance(r, str) else (r.get("text") or r.get("content") or str(r))
                chunks.append(KnowledgeChunk(text=str(text)[:800], source="cognee graph", score=1.0, kind="graph"))
            # Merge with structured local hits for section references.
            chunks.extend(self.fallback.search_policy(policy_id, query, top_k=3))
            return chunks[: top_k + 3]
        except Exception as exc:
            self.last_error = f"search: {exc}"
            logger.warning("Cognee search failed, falling back: %s", exc)
            return self.fallback.search_policy(policy_id, query, top_k)

    def get_related_requirements(self, policy_id: str, topic: str) -> List[str]:
        return self.fallback.get_related_requirements(policy_id, topic)

    def get_policy_context(self, policy_id: str, query: str) -> PolicyContext:
        ctx = self.fallback.get_policy_context(policy_id, query)
        if self.available:
            ctx.chunks = self.search_policy(policy_id, query, top_k=6)
            ctx.backend = self.name
        return ctx

    def status(self) -> Dict[str, Any]:
        return {
            "backend": self.name if self.available else "local",
            "configured": bool(self.settings.COGNEE_ENABLED),
            "available": self.available,
            "last_error": self.last_error,
        }
