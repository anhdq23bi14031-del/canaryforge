"""
Alert Dispatcher — sends notifications when a canary token fires.
Supports Email (SMTP) and Slack webhooks.
"""
import httpx
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

from backend.config import settings


async def dispatch_alert(
    trigger_id: str,
    token_id: str,
    token_name: str,
    token_type: str,
    ip_address: str,
    user_agent: str,
    risk_score: float,
    score_breakdown: dict,
    geo: dict,
    timestamp: datetime,
):
    """Fire all configured alert channels."""
    context = {
        "trigger_id": trigger_id,
        "token_id": token_id,
        "token_name": token_name,
        "token_type": token_type,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "risk_score": risk_score,
        "score_breakdown": score_breakdown,
        "geo": geo,
        "timestamp": timestamp.isoformat() if timestamp else "unknown",
    }

    if settings.SLACK_WEBHOOK_URL:
        await _send_slack(context)

    if settings.SMTP_HOST and settings.ALERT_TO_EMAIL:
        await _send_email(context)


async def _send_slack(ctx: dict):
    location = f"{ctx['geo'].get('city', '')}, {ctx['geo'].get('country', '')}".strip(", ")
    breakdown_lines = "\n".join(
        f"  • {k}: {v:+g}" for k, v in ctx["score_breakdown"].items()
    )

    payload = {
        "text": f":rotating_light: *CanaryForge Alert* — `{ctx['token_name']}` triggered",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 Canary Token Triggered"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Token:*\n{ctx['token_name']}"},
                    {"type": "mrkdwn", "text": f"*Type:*\n{ctx['token_type'].upper()}"},
                    {"type": "mrkdwn", "text": f"*IP Address:*\n`{ctx['ip_address']}`"},
                    {"type": "mrkdwn", "text": f"*Location:*\n{location or 'Unknown'}"},
                    {"type": "mrkdwn", "text": f"*Risk Score:*\n{ctx['risk_score']}/100"},
                    {"type": "mrkdwn", "text": f"*Time:*\n{ctx['timestamp']}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*User-Agent:*\n```{ctx['user_agent'][:200]}```",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Score Breakdown:*\n```{breakdown_lines}```",
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Trigger ID: `{ctx['trigger_id']}` | Token ID: `{ctx['token_id']}`",
                    }
                ],
            },
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"[CanaryForge] Slack alert failed: {e}")


async def _send_email(ctx: dict):
    location = f"{ctx['geo'].get('city', '')}, {ctx['geo'].get('country', '')}".strip(", ")
    breakdown_html = "".join(
        f"<tr><td style='padding:4px 8px'>{k}</td><td style='padding:4px 8px;color:{'#dc2626' if v > 0 else '#16a34a'}'>{v:+g}</td></tr>"
        for k, v in ctx["score_breakdown"].items()
    )

    html_body = f"""
<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:600px;margin:0 auto">
  <div style="background:#dc2626;color:white;padding:20px 24px;border-radius:8px 8px 0 0">
    <h1 style="margin:0;font-size:20px">🚨 Canary Token Triggered</h1>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
    <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
      <tr><td style="padding:6px 0;color:#666;width:140px">Token</td><td><strong>{ctx['token_name']}</strong></td></tr>
      <tr><td style="padding:6px 0;color:#666">Type</td><td>{ctx['token_type'].upper()}</td></tr>
      <tr><td style="padding:6px 0;color:#666">IP Address</td><td><code>{ctx['ip_address']}</code></td></tr>
      <tr><td style="padding:6px 0;color:#666">Location</td><td>{location or 'Unknown'}</td></tr>
      <tr><td style="padding:6px 0;color:#666">Risk Score</td><td><strong>{ctx['risk_score']}/100</strong></td></tr>
      <tr><td style="padding:6px 0;color:#666">Time</td><td>{ctx['timestamp']}</td></tr>
      <tr><td style="padding:6px 0;color:#666">User-Agent</td><td style="font-size:12px">{ctx['user_agent'][:200]}</td></tr>
    </table>
    <h3 style="margin-bottom:8px;color:#374151">Score Breakdown</h3>
    <table style="border-collapse:collapse;background:#f9fafb;border-radius:6px;width:100%">
      {breakdown_html}
    </table>
    <p style="margin-top:20px;font-size:12px;color:#9ca3af">
      Trigger ID: {ctx['trigger_id']}<br>Token ID: {ctx['token_id']}
    </p>
  </div>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[CanaryForge] 🚨 Token triggered: {ctx['token_name']} from {ctx['ip_address']}"
    msg["From"] = settings.ALERT_FROM_EMAIL
    msg["To"] = settings.ALERT_TO_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        context_ssl = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls(context=context_ssl)
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.ALERT_FROM_EMAIL, settings.ALERT_TO_EMAIL, msg.as_string())
    except Exception as e:
        print(f"[CanaryForge] Email alert failed: {e}")
