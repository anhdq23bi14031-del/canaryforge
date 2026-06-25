"""
Alerts API — list and inspect trigger events.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from backend.database import get_db, Trigger

router = APIRouter()


@router.get("/")
async def list_triggers(
    token_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    only_alerts: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    q = select(Trigger).order_by(Trigger.timestamp.desc()).limit(limit).offset(offset)
    if token_id:
        q = q.where(Trigger.token_id == token_id)
    if only_alerts:
        q = q.where(Trigger.alert_fired == True)  # noqa

    result = await db.execute(q)
    triggers = result.scalars().all()

    return [_serialize(t) for t in triggers]


@router.get("/{trigger_id}")
async def get_trigger(trigger_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Trigger).where(Trigger.id == trigger_id))
    t = result.scalar_one_or_none()
    if not t:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Trigger not found")
    return _serialize(t)


def _serialize(t: Trigger) -> dict:
    return {
        "id": t.id,
        "token_id": t.token_id,
        "token_type": t.token_type,
        "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        "ip_address": t.ip_address,
        "user_agent": t.user_agent,
        "referer": t.referer,
        "geo_country": t.geo_country,
        "geo_city": t.geo_city,
        "risk_score": t.risk_score,
        "score_breakdown": t.score_breakdown,
        "is_false_positive": t.is_false_positive,
        "alert_fired": t.alert_fired,
    }
