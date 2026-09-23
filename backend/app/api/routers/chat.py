from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User
from app.schemas.api import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(req: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ask COVE2E — context-aware entry point. Sarvam detects intent; FastAPI routes to the specialised agent."""
    response = orchestrator.chat(db, user, req)
    db.commit()
    return response
