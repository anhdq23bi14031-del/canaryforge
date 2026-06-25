"""
HTML Canary Token — generates a decoy web page with an embedded tracker.
Useful for planting as a fake internal portal, admin panel, or login page.
"""
import secrets
from backend.config import settings


def generate_html_token(token_id: str, name: str, page_type: str = "login") -> dict:
    """
    Generate a convincing fake HTML page with an embedded canary pixel.

    page_type options: login, admin, portal, docs
    """
    slug = secrets.token_urlsafe(16)
    tracking_url = f"{settings.BASE_URL}/c/h/{token_id}/{slug}"

    html = _build_page(page_type, tracking_url, name)

    return {
        "token_value": tracking_url,
        "slug": slug,
        "metadata": {
            "name": name,
            "type": "html",
            "tracking_url": tracking_url,
            "page_type": page_type,
            "html_content": html,
            "instructions": (
                f"Host this HTML file on an internal web server or S3 static site. "
                f"Any visit to the page triggers the canary via {tracking_url}."
            ),
        },
    }


def _build_page(page_type: str, tracking_url: str, name: str) -> str:
    pixel = f'<img src="{tracking_url}" width="1" height="1" style="position:absolute;opacity:0;" alt="">'

    pages = {
        "login": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Internal Portal — Sign In</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f0f2f5; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; }}
  .card {{ background: white; border-radius: 8px; padding: 40px;
           width: 380px; box-shadow: 0 2px 16px rgba(0,0,0,.12); }}
  h1 {{ font-size: 22px; color: #1a1a2e; margin-bottom: 8px; }}
  p {{ color: #666; font-size: 13px; margin-bottom: 28px; }}
  label {{ display: block; font-size: 13px; font-weight: 500;
           color: #333; margin-bottom: 6px; }}
  input {{ width: 100%; padding: 10px 12px; border: 1px solid #ddd;
           border-radius: 6px; font-size: 14px; margin-bottom: 16px; }}
  button {{ width: 100%; padding: 11px; background: #2563eb; color: white;
            border: none; border-radius: 6px; font-size: 14px;
            font-weight: 600; cursor: pointer; }}
</style>
</head>
<body>
{pixel}
<div class="card">
  <h1>Internal Portal</h1>
  <p>Sign in with your corporate credentials to continue.</p>
  <label>Email address</label>
  <input type="email" placeholder="you@company.internal">
  <label>Password</label>
  <input type="password" placeholder="••••••••">
  <button type="button">Sign in</button>
</div>
</body>
</html>""",

        "admin": f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Admin Console</title>
<style>
  body {{ font-family: monospace; background: #0f172a; color: #94a3b8;
         padding: 40px; }}
  h1 {{ color: #e2e8f0; font-size: 20px; margin-bottom: 4px; }}
  .badge {{ display: inline-block; background: #dc2626; color: white;
            font-size: 10px; padding: 2px 8px; border-radius: 4px;
            text-transform: uppercase; margin-bottom: 32px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 10px 16px; border-bottom: 1px solid #1e293b; }}
  th {{ color: #64748b; font-size: 11px; text-transform: uppercase; }}
</style>
</head>
<body>
{pixel}
<h1>Infrastructure Admin Console</h1>
<span class="badge">Restricted Access</span>
<table>
  <tr><th>Service</th><th>Host</th><th>Status</th></tr>
  <tr><td>Database Primary</td><td>db-01.corp.internal</td><td>● Online</td></tr>
  <tr><td>Cache Cluster</td><td>redis-01.corp.internal</td><td>● Online</td></tr>
  <tr><td>Auth Service</td><td>auth.corp.internal</td><td>● Online</td></tr>
</table>
</body>
</html>""",
    }

    return pages.get(page_type, pages["login"])
