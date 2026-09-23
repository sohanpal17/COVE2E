"""Deterministic mock insurer.

Exposed over HTTP under /mock-insurer (called by n8n) and used directly by the
demo fallback executor. State lives in the mock_insurer_claims table.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.enums import InsurerClaimStatus as ST, PaymentStatus, SettlementStatus
from app.models import MockInsurerClaim

REQUIRED_DOCS_BY_PRODUCT: Dict[str, Dict[str, List[str]]] = {
    "HEALTH": {
        "REIMBURSEMENT": ["claim_form", "policy_copy", "id_proof", "hospital_bill", "discharge_summary", "medical_certificate"],
        "CASHLESS": ["claim_form", "policy_copy", "id_proof", "medical_certificate"],
    },
    "MOTOR": {
        "OWN_DAMAGE": ["claim_form", "policy_copy", "driving_license", "rc_copy", "repair_estimate", "damage_photos"],
        "THIRD_PARTY": ["claim_form", "policy_copy", "driving_license", "rc_copy", "fir_copy"],
    },
    "GADGET": {
        "GADGET": ["claim_form", "policy_copy", "purchase_invoice", "fir_copy"],
    },
}

QUERY_MESSAGES = {
    "medical_certificate": "Please provide the medical certificate from the treating doctor confirming diagnosis and treatment.",
    "discharge_summary": "Please provide the hospital discharge summary.",
    "hospital_bill": "Please provide the itemised final hospital bill.",
    "fir_copy": "Please provide a copy of the FIR / police report.",
    "repair_estimate": "Please provide the garage repair estimate.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MockInsurerService:
    def __init__(self, db: Session):
        self.db = db

    # ---- helpers ----
    def get(self, external_id: str) -> Optional[MockInsurerClaim]:
        return self.db.get(MockInsurerClaim, external_id)

    def get_or_404(self, external_id: str) -> MockInsurerClaim:
        claim = self.get(external_id)
        if not claim:
            raise KeyError(external_id)
        return claim

    @staticmethod
    def snapshot(claim: MockInsurerClaim) -> Dict[str, Any]:
        return {
            "external_claim_id": claim.id,
            "claim_number": claim.claim_number,
            "status": claim.status,
            "settlement_status": claim.settlement_status,
            "payment_status": claim.payment_status,
            "documents": claim.documents,
            "open_queries": [q for q in claim.queries if q.get("status") == "OPEN"],
            "queries": claim.queries,
            "required_documents": claim.required_documents,
            "history": claim.history[-10:],
            "updated_at": claim.updated_at.isoformat() if claim.updated_at else None,
        }

    def _log(self, claim: MockInsurerClaim, event: str, detail: str = "", **extra: Any) -> None:
        claim.history = list(claim.history) + [{"at": _now(), "event": event, "detail": detail, **extra}]

    def _present_types(self, claim: MockInsurerClaim) -> set:
        return {d.get("document_type") for d in claim.documents}

    def _missing_required(self, claim: MockInsurerClaim) -> List[str]:
        present = self._present_types(claim)
        return [d for d in claim.required_documents if d not in present]

    # ---- operations ----
    def create_claim(
        self,
        *,
        claim_number: str,
        policy_number: str,
        product_type: str,
        claim_type: str,
        claimed_amount: float,
        documents: List[Dict[str, Any]],
        external_id: Optional[str] = None,
    ) -> MockInsurerClaim:
        external_id = external_id or f"INS-{claim_number}"
        existing = self.get(external_id)
        if existing:
            return existing
        required = REQUIRED_DOCS_BY_PRODUCT.get(product_type, {}).get(claim_type)
        if required is None:
            required = next(iter(REQUIRED_DOCS_BY_PRODUCT.get(product_type, {"_": []}).values()))
        claim = MockInsurerClaim(
            id=external_id,
            claim_number=claim_number,
            policy_number=policy_number,
            product_type=product_type,
            claim_type=claim_type,
            status=ST.SUBMITTED,
            claimed_amount=claimed_amount,
            documents=list(documents),
            queries=[],
            history=[],
            required_documents=list(required),
        )
        self._log(claim, "CLAIM_RECEIVED", "Claim received by insurer")
        self.db.add(claim)
        self.db.flush()
        self._evaluate(claim)
        self.db.flush()
        return claim

    def attach_document(self, external_id: str, document: Dict[str, Any]) -> MockInsurerClaim:
        claim = self.get_or_404(external_id)
        docs = [d for d in claim.documents if d.get("document_type") != document.get("document_type")]
        docs.append({**document, "received_at": _now()})
        claim.documents = docs
        self._log(claim, "DOCUMENT_RECEIVED", f"Document received: {document.get('document_type')}", document_type=document.get("document_type"))
        self.db.flush()
        return claim

    def resubmit(self, external_id: str) -> MockInsurerClaim:
        claim = self.get_or_404(external_id)
        self._log(claim, "RESUBMITTED", "Claim resubmitted for review")
        self._evaluate(claim)
        self.db.flush()
        return claim

    def raise_query(self, external_id: str, message: str, requested_document_type: Optional[str]) -> MockInsurerClaim:
        claim = self.get_or_404(external_id)
        query = {
            "id": f"Q-{len(claim.queries) + 1}",
            "message": message,
            "requested_document_type": requested_document_type,
            "status": "OPEN",
            "raised_at": _now(),
        }
        claim.queries = list(claim.queries) + [query]
        claim.status = ST.DOCUMENT_PENDING
        self._log(claim, "QUERY_RAISED", message, query_id=query["id"])
        self.db.flush()
        return claim

    def record_follow_up(self, external_id: str, message: str) -> MockInsurerClaim:
        """User → insurer follow-up on a delayed claim. Does not change status."""
        claim = self.get_or_404(external_id)
        self._log(claim, "FOLLOW_UP", message)
        self.db.flush()
        return claim

    def transition(
        self,
        external_id: str,
        status: Optional[str] = None,
        settlement_status: Optional[str] = None,
        payment_status: Optional[str] = None,
        note: str = "",
    ) -> MockInsurerClaim:
        """Demo control endpoint. Lets the demo place the insurer in any deterministic state."""
        claim = self.get_or_404(external_id)
        before = claim.status
        if status:
            claim.status = status
        if settlement_status:
            claim.settlement_status = settlement_status
        if payment_status:
            claim.payment_status = payment_status
        self._log(claim, "MANUAL_TRANSITION", note or f"{before} -> {claim.status}")
        self.db.flush()
        return claim

    def _evaluate(self, claim: MockInsurerClaim) -> None:
        """Deterministic review rule: any required document missing → DOCUMENT_PENDING with a query;
        otherwise UNDER_REVIEW and all open queries are resolved."""
        missing = self._missing_required(claim)
        if missing:
            claim.status = ST.DOCUMENT_PENDING
            open_types = {q.get("requested_document_type") for q in claim.queries if q.get("status") == "OPEN"}
            for doc_type in missing:
                if doc_type not in open_types:
                    query = {
                        "id": f"Q-{len(claim.queries) + 1}",
                        "message": QUERY_MESSAGES.get(doc_type, f"Please provide the {doc_type.replace('_', ' ')}."),
                        "requested_document_type": doc_type,
                        "status": "OPEN",
                        "raised_at": _now(),
                    }
                    claim.queries = list(claim.queries) + [query]
                    self._log(claim, "QUERY_RAISED", query["message"], query_id=query["id"])
            self._log(claim, "STATUS", "DOCUMENT_PENDING", missing=missing)
        else:
            resolved = []
            for q in claim.queries:
                if q.get("status") == "OPEN":
                    q = {**q, "status": "RESOLVED", "resolved_at": _now()}
                resolved.append(q)
            claim.queries = resolved
            claim.status = ST.UNDER_REVIEW
            self._log(claim, "STATUS", "UNDER_REVIEW - all required documents present")

    def has_conflict(self, claim: MockInsurerClaim) -> Optional[str]:
        """Detect internally inconsistent external state."""
        if claim.payment_status == PaymentStatus.COMPLETED and claim.settlement_status != SettlementStatus.COMPLETED:
            return "Payment is marked COMPLETED while settlement is still PENDING."
        if claim.status in {ST.REJECTED} and claim.payment_status == PaymentStatus.COMPLETED:
            return "Claim is REJECTED but payment is COMPLETED."
        if claim.status == ST.APPROVED and claim.settlement_status == SettlementStatus.PENDING and claim.payment_status == PaymentStatus.COMPLETED:
            return "Claim APPROVED, settlement PENDING, payment COMPLETED — these states cannot all be true."
        return None
