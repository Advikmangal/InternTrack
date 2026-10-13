from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..auth import current_user
from ..database import get_db
from ..models import Application, Interview, FollowUp, now
from ..services import serialize

router = APIRouter(prefix='/api/dashboard', tags=['Dashboard'])


@router.get('')
def dashboard(user=Depends(current_user), db: Session = Depends(get_db)):
    apps = list(db.scalars(select(Application).where(Application.user_id == user.id)))
    today = datetime.now(ZoneInfo(user.timezone)).date()
    upcoming = list(db.execute(select(Interview, Application.company).join(Application).where(
        Application.user_id == user.id, Interview.starts_at >= now()).order_by(Interview.starts_at)))
    followups = list(db.execute(select(FollowUp, Application.company).join(Application).where(
        Application.user_id == user.id, FollowUp.completed_at.is_(None)).order_by(FollowUp.due_date)))
    distribution = Counter(a.status for a in apps)
    timeline = Counter(a.application_date.isoformat() for a in apps if a.status != 'Saved' and a.application_date)
    return {'submitted': sum(a.status != 'Saved' for a in apps),
            'active': sum(a.status in ('Applied', 'Assessment', 'Interview') for a in apps),
            'offers': distribution['Offer'], 'upcoming_interviews': len(upcoming),
            'overdue_followups': sum(f.due_date < today for f, _ in followups),
            'today_followups': sum(f.due_date == today for f, _ in followups),
            'upcoming_followups': sum(f.due_date > today for f, _ in followups),
            'distribution': dict(distribution), 'timeline': dict(sorted(timeline.items())),
            'interviews': [{**serialize(i), 'company': c} for i, c in upcoming[:5]],
            'followups': [{**serialize(f), 'company': c} for f, c in followups[:5]],
            'recent': [serialize(a) for a in sorted(apps, key=lambda a: a.updated_at, reverse=True)[:5]]}
