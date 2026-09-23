"""n8n workflow trigger adapter.

FastAPI decides WHICH workflow runs (after the Action Gate). n8n executes it by
calling the mock insurer endpoints and responds with a structured result.

If n8n is unreachable and DEMO_MODE is on, callers may use the clearly labelled
demo fallback executor (see services/workflow_executor.py). In production mode
the failure is surfaced, never hidden.
"""
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

WORKFLOWS = {
    "claim_submission": "cove2e-claim-submission",
    "recovery": "cove2e-recovery",
    "document": "cove2e-document",
    "notification": "cove2e-notification",
    "escalation": "cove2e-escalation",
    "status_polling": "cove2e-status-polling",
}


class N8nUnavailable(Exception):
    pass


class N8nClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.last_error: Optional[str] = None
        self.last_success: bool = False

    def webhook_url(self, workflow: str) -> str:
        path = WORKFLOWS.get(workflow, workflow)
        return f"{self.settings.N8N_BASE_URL.rstrip('/')}/webhook/{path}"

    def status(self) -> Dict[str, Any]:
        return {
            "base_url": self.settings.N8N_BASE_URL,
            "reachable": self.ping(),
            "last_error": self.last_error,
            "workflows": WORKFLOWS,
        }

    def ping(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.settings.N8N_BASE_URL.rstrip('/')}/healthz")
                return resp.status_code < 500
        except Exception:
            return False

    def trigger(self, workflow: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronously trigger an n8n webhook workflow and return its JSON response."""
        body = {
            **payload,
            "backend_url": self.settings.BACKEND_PUBLIC_URL,
            "workflow": workflow,
        }
        headers = {"X-COVE2E-Secret": self.settings.N8N_WEBHOOK_SECRET, "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.settings.N8N_TIMEOUT_SECONDS) as client:
                resp = client.post(self.webhook_url(workflow), json=body, headers=headers)
                resp.raise_for_status()
                self.last_error = None
                self.last_success = True
                try:
                    return resp.json()
                except ValueError:
                    return {"ok": True, "raw": resp.text}
        except Exception as exc:
            self.last_error = f"{workflow}: {exc}"
            self.last_success = False
            logger.warning("n8n trigger failed for %s: %s", workflow, exc)
            raise N8nUnavailable(str(exc)) from exc


_client: Optional[N8nClient] = None


def get_n8n() -> N8nClient:
    global _client
    if _client is None:
        _client = N8nClient()
    return _client
