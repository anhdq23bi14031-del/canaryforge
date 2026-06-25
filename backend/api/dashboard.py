"""
Dashboard API — aggregated stats for the frontend.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from datetime import datetime, timezone, timedelta

from backend.database import get_db, Token, Trigger

router = APIRouter()


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    # Total tokens
    total_tokens = (await db.execute(select(func.count(Token.id)))).scalar()

    # Active tokens
    active_tokens = (await db.execute(
        select(func.count(Token.id)).where(Token.is_active == True)  # noqa
    )).scalar()

    # Total triggers
    total_triggers = (await db.execute(select(func.count(Trigger.id)))).scalar()

    # Real alerts (non-FP, alert_fired)
    real_alerts = (await db.execute(
        select(func.count(Trigger.id)).where(
            Trigger.alert_fired == True  # noqa
        )
    )).scalar()

    # Triggers last 24h
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_triggers = (await db.execute(
        select(func.count(Trigger.id)).where(Trigger.timestamp >= since)
    )).scalar()

    # Triggers by type
    type_counts_result = await db.execute(
        select(Trigger.token_type, func.count(Trigger.id))
        .group_by(Trigger.token_type)
    )
    triggers_by_type = {row[0]: row[1] for row in type_counts_result}

    # Top triggered tokens
    top_tokens_result = await db.execute(
        select(Token.id, Token.name, Token.token_type, Token.trigger_count)
        .order_by(Token.trigger_count.desc())
        .limit(5)
    )
    top_tokens = [
        {"id": r[0], "name": r[1], "type": r[2], "trigger_count": r[3]}
        for r in top_tokens_result
    ]

    # Recent alerts
    recent_alerts_result = await db.execute(
        select(Trigger)
        .where(Trigger.alert_fired == True)  # noqa
        .order_by(Trigger.timestamp.desc())
        .limit(10)
    )
    recent_alert_list = [
        {
            "id": t.id,
            "token_id": t.token_id,
            "token_type": t.token_type,
            "ip_address": t.ip_address,
            "geo_country": t.geo_country,
            "risk_score": t.risk_score,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        }
        for t in recent_alerts_result.scalars()
    ]

    return {
        "total_tokens": total_tokens,
        "active_tokens": active_tokens,
        "total_triggers": total_triggers,
        "real_alerts": real_alerts,
        "recent_triggers_24h": recent_triggers,
        "triggers_by_type": triggers_by_type,
        "top_tokens": top_tokens,
        "recent_alerts": recent_alert_list,
    }
