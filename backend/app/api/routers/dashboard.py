from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditLog, User
from app.schemas.api import AuditLogOut, DashboardResponse, IntegrationStatus
from app.services.dashboard_service import build_dashboard, integrations_status

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_dashboard(db, user)


@router.get("/integrations", response_model=IntegrationStatus)
def integrations(db: Session = Depends(get_db)):
    return IntegrationStatus(**integrations_status(db))


@router.get("/audit", response_model=List[AuditLogOut])
def audit(limit: int = 50, journey_id: str | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(AuditLog).filter(AuditLog.user_id == user.id)
    if journey_id:
        q = q.filter(AuditLog.journey_id == journey_id)
    return q.order_by(AuditLog.created_at.desc()).limit(min(limit, 200)).all()
