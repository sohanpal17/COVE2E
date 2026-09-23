from typing import Optional

from sqlalchemy.orm import Session

from app.core.enums import NotificationKind
from app.models import Notification


def notify(
    db: Session,
    user_id: str,
    title: str,
    message: str,
    *,
    kind: NotificationKind | str = NotificationKind.INFO,
    journey_id: Optional[str] = None,
    claim_id: Optional[str] = None,
    link: str = "",
) -> Notification:
    n = Notification(user_id=user_id, title=title, message=message, kind=str(kind), journey_id=journey_id, claim_id=claim_id, link=link)
    db.add(n)
    db.flush()
    return n
