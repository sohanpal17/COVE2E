"""Dashboard aggregation: coverage, journeys, action required, important dates, greeting."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import JourneyState
from app.core.timeutil import aware
from app.integrations.n8n_client import get_n8n
from app.integrations.sarvam_client import get_sarvam
from app.models import Claim, Journey, Notification, User
from app.schemas.api import ActionRequiredItem, ClaimSummary, DashboardResponse, ImportantDate, JourneyOut, UserOut
from app.services.claim_service import list_claims
from app.services.journey_service import list_journeys
from app.services.policy_knowledge import knowledge_status
from app.services.policy_service import days_to_expiry, list_policies, to_summary

SUGGESTED_ACTIONS = [
    {"key": "understand_policy", "label": "Understand my policy", "link": "/policies"},
    {"key": "start_claim", "label": "Start a claim", "link": "/incidents"},
    {"key": "readiness", "label": "Check claim readiness", "link": "/claims"},
    {"key": "missing_docs", "label": "Find missing documents", "link": "/claims"},
    {"key": "track", "label": "Track my claim", "link": "/claims"},
    {"key": "recover", "label": "Recover my stuck claim", "link": "/journeys"},
    {"key": "compare", "label": "Compare insurance", "link": "/discovery"},
]


def integrations_status(db: Session) -> Dict[str, Any]:
    settings = get_settings()
    return {
        "sarvam": get_sarvam().status(),
        "cognee": knowledge_status(db),
        "n8n": get_n8n().status(),
        "database": {"url": settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL, "dialect": settings.DATABASE_URL.split(":")[0]},
        "demo_mode": settings.DEMO_MODE,
    }


def build_dashboard(db: Session, user: User) -> DashboardResponse:
    policies = list_policies(db, user)
    journeys = list_journeys(db, user)
    claims = list_claims(db, user)
    now = datetime.now(timezone.utc)

    action_required: List[ActionRequiredItem] = []
    for c in claims:
        open_q = [q for q in c.queries if q.status == "OPEN"]
        if open_q:
            action_required.append(ActionRequiredItem(title=f"{c.claim_number}: insurer requested a document", detail=open_q[0].message, link=f"/journeys/{c.journey_id}/investigation", journey_id=c.journey_id, claim_id=c.id, severity="BLOCKED"))
        elif c.status == "DRAFT":
            missing = [r.label for r in c.requirements if r.required and r.status == "MISSING"]
            if missing:
                action_required.append(ActionRequiredItem(title=f"{c.claim_number}: {len(missing)} document{'s' if len(missing) != 1 else ''} required", detail=", ".join(missing), link=f"/claims/{c.id}/documents", journey_id=c.journey_id, claim_id=c.id))
    for j in journeys:
        if j.current_state == JourneyState.ESCALATED:
            action_required.append(ActionRequiredItem(title=f"{j.title}: with a human agent", detail="An escalation is open for this journey.", link=f"/journeys/{j.id}/recovery", journey_id=j.id, claim_id=j.claim_id, severity="ESCALATED"))

    dates: List[ImportantDate] = []
    for p in policies:
        if p.end_date:
            d = days_to_expiry(p) or 0
            dates.append(ImportantDate(label=f"{p.policy_type.title()} policy expires ({p.insurer})", date=aware(p.end_date), kind="EXPIRY", days_from_now=d, policy_id=p.id))
        if p.start_date and p.waiting_period_days:
            wp_end = aware(p.start_date) + timedelta(days=p.waiting_period_days)
            if wp_end > now:
                dates.append(ImportantDate(label=f"Waiting period ends ({p.plan_name or p.insurer})", date=wp_end, kind="WAITING_PERIOD", days_from_now=(wp_end - now).days, policy_id=p.id))
    for c in claims:
        for q in c.queries:
            if q.status == "OPEN":
                deadline = aware(q.raised_at) + timedelta(days=15)
                dates.append(ImportantDate(label=f"Respond to insurer query ({c.claim_number})", date=deadline, kind="CLAIM_DEADLINE", days_from_now=(deadline - now).days, claim_id=c.id))
    dates.sort(key=lambda d: d.date)

    unread = db.query(Notification).filter(Notification.user_id == user.id, Notification.read.is_(False)).count()
    greeting = _greeting(user, policies, claims, journeys, now)

    return DashboardResponse(
        user=UserOut.model_validate(user),
        policies=[to_summary(p) for p in policies],
        journeys=[JourneyOut.model_validate(j) for j in journeys],
        claims=[ClaimSummary.model_validate(c) for c in claims],
        action_required=action_required,
        important_dates=dates[:8],
        unread_notifications=unread,
        greeting=greeting,
        suggested_actions=SUGGESTED_ACTIONS,
        integrations=integrations_status(db),
    )


def _greeting(user: User, policies, claims: List[Claim], journeys: List[Journey], now: datetime) -> str:
    hour = now.hour + 5  # rough IST offset for the greeting only
    part = "Good morning" if hour % 24 < 12 else ("Good afternoon" if hour % 24 < 17 else "Good evening")
    lines = [f"{part}, {user.name.split(' ')[0]}."]
    expiring = sorted([(days_to_expiry(p), p) for p in policies if p.end_date], key=lambda t: t[0])
    if expiring:
        d, p = expiring[0]
        lines.append(f"Your {p.policy_type.lower()} policy expires in {d} days.")
    active = [c for c in claims if c.status not in {"SETTLED", "REJECTED"}]
    # Surface the blocked claim first (open insurer query), then anything else active.
    active.sort(key=lambda c: (0 if any(q.status == "OPEN" for q in c.queries) else 1))
    if active:
        c = active[0]
        lines.append(f"You have an active {c.incident_type.replace('_', ' ')} claim ({c.claim_number}).")
        open_q = [q for q in c.queries if q.status == "OPEN"]
        if open_q:
            lines.append("It is currently waiting for an additional document.")
        elif c.status == "DRAFT":
            missing = [r for r in c.requirements if r.required and r.status == "MISSING"]
            if missing:
                lines.append(f"It needs {len(missing)} more document{'s' if len(missing) != 1 else ''} before submission.")
        elif c.status == "UNDER_REVIEW":
            lines.append("It is under review with the insurer; no action is currently required.")
    escalated = [j for j in journeys if j.current_state == JourneyState.ESCALATED]
    if escalated:
        lines.append("One journey is with a human agent.")
    lines.append("What would you like to work on?")
    return "\n".join(lines)
