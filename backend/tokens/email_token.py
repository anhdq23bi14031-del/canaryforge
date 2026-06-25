"""
Email Canary Token — a 1x1 tracking pixel for embedding in emails.
When the email is opened, the pixel is fetched and the canary fires.
"""
import secrets
from backend.config import settings


def generate_email_token(token_id: str, name: str) -> dict:
    """
    Returns a tracking pixel URL and ready-to-use HTML snippet.
    """
    slug = secrets.token_urlsafe(16)
    tracking_url = f"{settings.BASE_URL}/img/{slug}.gif"

    pixel_html = (
        f'<img src="{tracking_url}" width="1" height="1" '
        f'style="display:none;border:0;" alt="" />'
    )

    return {
        "token_value": tracking_url,
        "slug": slug,
        "metadata": {
            "name": name,
            "type": "email",
            "slug": slug,
            "tracking_url": tracking_url,
            "pixel_html": pixel_html,
            "instructions": (
                "Embed the pixel_html snippet at the bottom of your email HTML body. "
                "When a recipient opens the email, the canary fires."
            ),
        },
    }