"""
Capture Server — receives inbound requests when canary tokens are triggered.
Fingerprints the requester, scores the behavior, logs the event, and fires alerts.
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
import httpx

from backend.database import get_db, Token, Trigger
from backend.scoring.engine import score_trigger
from backend.alerting.dispatcher import dispatch_alert

router = APIRouter()

# 1x1 transparent GIF — returned for pixel-type tokens
TRANSPARENT_GIF = (
    b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00"
    b"\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x00\x00\x00\x00"
    b"\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02"
    b"\x44\x01\x00\x3b"
)


@router.get("/files/{slug}")
async def capture_url(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """URL canary token trigger. Looks like a normal file-share link."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "url", request, db)
    return Response(status_code=204)


@router.get("/assets/{slug}.png")
async def capture_doc(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Document canary token trigger (embedded image/link fetch). Looks like a static asset."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "doc", request, db)
    return Response(content=TRANSPARENT_GIF, media_type="image/gif")


@router.get("/img/{slug}.gif")
async def capture_email(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Email tracking pixel trigger. Looks like a normal image asset."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "email", request, db)
    return Response(content=TRANSPARENT_GIF, media_type="image/gif")


@router.get("/static/{slug}")
async def capture_html(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """HTML page canary trigger. Looks like a normal static page."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "html", request, db)
    return Response(content=TRANSPARENT_GIF, media_type="image/gif")


@router.get("/view/{slug}")
async def capture_pdf(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """PDF canary token trigger (clickable in-document link). Looks like a doc viewer link."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "pdf", request, db)
    return Response(status_code=204)


@router.get("/sheets/{slug}")
async def capture_excel(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Excel canary token trigger (hyperlink cell). Looks like a normal sheet reference link."""
    token_id = await _resolve_slug(slug, db)
    await _handle_trigger(token_id, "excel", request, db)
    return Response(status_code=204)


async def _resolve_slug(slug: str, db: AsyncSession) -> str:
    """
    Look up which token a slug belongs to via the indexed Token.slug column.
    The public URL never has to expose the internal token_id.
    """
    result = await db.execute(select(Token).where(Token.slug == slug))
    token = result.scalar_one_or_none()
    if not token:
        return "unknown"
    return token.id


async def _handle_trigger(
    token_id: str,
    token_type: str,
    request: Request,
    db: AsyncSession,
):
    """Core trigger handler: fingerprint → score → log → alert."""

    # --- Fingerprint ---
    ip = _get_real_ip(request)
    ua = request.headers.get("user-agent", "")
    referer = request.headers.get("referer", "")
    headers_dict = dict(request.headers)

    geo = await _geolocate(ip)

    # --- Score ---
    score = score_trigger(
        ip_address=ip,
        user_agent=ua,
        referer=referer,
        headers=headers_dict,
        geo_country=geo.get("country_code"),
        token_type=token_type,
    )

    # --- Persist trigger ---
    trigger = Trigger(
        token_id=token_id,
        token_type=token_type,
        ip_address=ip,
        user_agent=ua,
        referer=referer,
        geo_country=geo.get("country_code"),
        geo_city=geo.get("city"),
        headers=headers_dict,
        risk_score=score.total,
        score_breakdown=score.breakdown,
        is_false_positive=score.is_false_positive,
        alert_fired=False,
    )
    db.add(trigger)

    # --- Increment token counter ---
    await db.execute(
        update(Token)
        .where(Token.id == token_id)
        .values(trigger_count=Token.trigger_count + 1)
    )

    await db.commit()
    await db.refresh(trigger)

    # --- Alert if score warrants it ---
    if score.recommendation == "alert":
        token_result = await db.execute(select(Token).where(Token.id == token_id))
        token = token_result.scalar_one_or_none()
        token_name = token.name if token else token_id

        await dispatch_alert(
            trigger_id=trigger.id,
            token_id=token_id,
            token_name=token_name,
            token_type=token_type,
            ip_address=ip,
            user_agent=ua,
            risk_score=score.total,
            score_breakdown=score.breakdown,
            geo=geo,
            timestamp=trigger.timestamp,
        )

        trigger.alert_fired = True
        await db.commit()


def _get_real_ip(request: Request) -> str:
    """Extract real IP, respecting common proxy headers."""
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _geolocate(ip: str) -> dict:
    """
    Lightweight IP geolocation using ip-api.com (free tier, no key needed).
    Falls back to empty dict on failure.
    """
    if ip in ("unknown", "127.0.0.1", "::1") or ip.startswith("192.168.") or ip.startswith("10."):
        return {"country_code": "LOCAL", "city": "localhost"}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"http://ip-api.com/json/{ip}?fields=country,countryCode,city,isp")
            if r.status_code == 200:
                data = r.json()
                return {
                    "country_code": data.get("countryCode", ""),
                    "country": data.get("country", ""),
                    "city": data.get("city", ""),
                    "isp": data.get("isp", ""),
                }
    except Exception:
        pass
    return {}