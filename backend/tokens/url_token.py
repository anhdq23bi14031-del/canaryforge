"""
URL Canary Token — generates a tracking URL that fires when visited.
"""
import secrets
from backend.config import settings


def generate_url_token(token_id: str, name: str) -> dict:
    """
    Returns the tracking URL and metadata for a URL canary token.
    """
    slug = secrets.token_urlsafe(16)
    tracking_url = f"{settings.BASE_URL}/files/{slug}"

    return {
        "token_value": tracking_url,
        "slug": slug,
        "metadata": {
            "name": name,
            "type": "url",
            "slug": slug,
            "tracking_url": tracking_url,
            "instructions": (
                f"Embed this URL in documents, emails, or web pages. "
                f"Any visit to {tracking_url} will trigger an alert."
            ),
        },
    }