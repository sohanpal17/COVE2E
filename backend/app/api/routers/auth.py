from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.enums import Actor, AuditAction
from app.core.security import create_access_token, get_current_user
from app.models import User
from app.schemas.api import DemoLoginRequest, TokenResponse, UpdateLanguageRequest, UserOut
from app.services import demo_service
from app.services.audit_service import record_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(req: DemoLoginRequest, db: Session = Depends(get_db)):
    user = demo_service.ensure_demo_user(db, req.demo_code)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown demo account. Use 'demo', 'demo-hi' or 'demo-mr'.")
    if req.language:
        user.preferred_language = req.language[:2]
    demo_service.ensure_products(db)
    record_audit(db, AuditAction.USER_LOGGED_IN, actor=Actor.USER, user_id=user.id, metadata={"demo_code": req.demo_code})
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/language", response_model=UserOut)
def set_language(req: UpdateLanguageRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.language[:2] not in {"en", "hi", "mr"}:
        raise HTTPException(status_code=400, detail="Supported languages: en, hi, mr")
    user.preferred_language = req.language[:2]
    db.commit()
    return UserOut.model_validate(user)
