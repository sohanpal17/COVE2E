from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.enums import Actor, AuditAction
from app.models import AuditLog


def record_audit(
    db: Session,
    action: AuditAction | str,
    *,
    actor: Actor | str = Actor.SYSTEM,
    user_id: Optional[str] = None,
    journey_id: Optional[str] = None,
    claim_id: Optional[str] = None,
    previous_state: Optional[str] = None,
    new_state: Optional[str] = None,
    result: str = "OK",
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        journey_id=journey_id,
        claim_id=claim_id,
        action=str(action),
        actor=str(actor),
        previous_state=previous_state,
        new_state=new_state,
        result=result,
        meta=metadata or {},
    )
    db.add(entry)
    db.flush()
    return entry
