"""
CanaryForge integration tests.
Run with: pytest tests/test_integration.py -v

These tests spin up the full FastAPI app in-process using httpx.AsyncClient
and an in-memory SQLite database — no external services needed.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Patch DB to use in-memory SQLite before importing app
import os
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("SECRET_KEY", "test-secret")

from backend.main import app
from backend.database import init_db, engine, Base


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create fresh tables before each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c


# ── Health ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Token creation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_url_token(client):
    r = await client.post("/api/tokens/", json={"name": "Test URL", "token_type": "url"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "url"
    assert "http://testserver/files/" in data["token_value"]
    assert data["metadata"]["instructions"]


@pytest.mark.asyncio
async def test_create_email_token(client):
    r = await client.post("/api/tokens/", json={"name": "Test Email", "token_type": "email"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "email"
    assert "pixel_html" in data["metadata"]
    assert 'width="1"' in data["metadata"]["pixel_html"]


@pytest.mark.asyncio
async def test_create_aws_token(client):
    r = await client.post("/api/tokens/", json={"name": "Test AWS", "token_type": "aws"})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "aws"
    meta = data["metadata"]
    assert meta["access_key_id"].startswith("CANA")
    assert len(meta["account_id"]) == 12
    assert meta["account_id"].isdigit()
    assert "credentials_file" in meta


@pytest.mark.asyncio
async def test_create_html_token(client):
    r = await client.post("/api/tokens/", json={"name": "Test HTML", "token_type": "html", "page_type": "login"})
    assert r.status_code == 200
    data = r.json()
    assert "html_content" in data["metadata"]
    assert "Internal Portal" in data["metadata"]["html_content"]


@pytest.mark.asyncio
async def test_create_doc_token_no_llm(client):
    """Doc token generation without LLM (use_llm=False)."""
    r = await client.post("/api/tokens/", json={
        "name": "Test Doc", "token_type": "doc",
        "content_type": "financial", "use_llm": False
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "doc"
    assert "tracking_url" in data["metadata"]


@pytest.mark.asyncio
async def test_create_pdf_token_no_llm(client):
    """PDF token generation without LLM (use_llm=False)."""
    r = await client.post("/api/tokens/", json={
        "name": "Test PDF", "token_type": "pdf",
        "content_type": "financial", "use_llm": False
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "pdf"
    assert "/view/" in data["token_value"]
    assert data["metadata"]["filename"].endswith(".pdf")


@pytest.mark.asyncio
async def test_create_excel_token_no_llm(client):
    """Excel token generation without LLM (use_llm=False)."""
    r = await client.post("/api/tokens/", json={
        "name": "Test Excel", "token_type": "excel",
        "content_type": "hr", "use_llm": False
    })
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "excel"
    assert "/sheets/" in data["token_value"]
    assert data["metadata"]["filename"].endswith(".xlsx")


@pytest.mark.asyncio
async def test_pdf_token_trigger(client):
    """Hitting a PDF token's click URL logs a trigger."""
    create = await client.post("/api/tokens/", json={
        "name": "PDF Canary", "token_type": "pdf", "use_llm": False
    })
    token_id = create.json()["id"]
    path = "/" + "/".join(create.json()["token_value"].split("/")[3:])

    r = await client.get(path)
    assert r.status_code == 204

    triggers = await client.get(f"/api/alerts/?token_id={token_id}")
    assert len(triggers.json()) == 1
    assert triggers.json()[0]["token_type"] == "pdf"


@pytest.mark.asyncio
async def test_excel_token_trigger(client):
    """Hitting an Excel token's sheet URL logs a trigger."""
    create = await client.post("/api/tokens/", json={
        "name": "Excel Canary", "token_type": "excel", "use_llm": False
    })
    token_id = create.json()["id"]
    path = "/" + "/".join(create.json()["token_value"].split("/")[3:])

    r = await client.get(path)
    assert r.status_code == 204

    triggers = await client.get(f"/api/alerts/?token_id={token_id}")
    assert len(triggers.json()) == 1
    assert triggers.json()[0]["token_type"] == "excel"


@pytest.mark.asyncio
async def test_pdf_download_returns_real_bytes(client):
    """Downloaded PDF should be non-empty and match stored bytes."""
    create = await client.post("/api/tokens/", json={
        "name": "PDF Dl", "token_type": "pdf", "use_llm": False
    })
    token_id = create.json()["id"]
    r = await client.get(f"/api/tokens/{token_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert len(r.content) > 100  # real PDF bytes, not empty


@pytest.mark.asyncio
async def test_excel_download_returns_real_bytes(client):
    """Downloaded Excel file should be non-empty and properly typed."""
    create = await client.post("/api/tokens/", json={
        "name": "Excel Dl", "token_type": "excel", "use_llm": False
    })
    token_id = create.json()["id"]
    r = await client.get(f"/api/tokens/{token_id}/download")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert len(r.content) > 100


@pytest.mark.asyncio
async def test_create_unknown_type(client):
    r = await client.post("/api/tokens/", json={"name": "Bad", "token_type": "unknown"})
    assert r.status_code == 400


# ── Token CRUD ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tokens(client):
    await client.post("/api/tokens/", json={"name": "A", "token_type": "url"})
    await client.post("/api/tokens/", json={"name": "B", "token_type": "email"})
    r = await client.get("/api/tokens/")
    assert r.status_code == 200
    assert len(r.json()) == 2


@pytest.mark.asyncio
async def test_get_token(client):
    create = await client.post("/api/tokens/", json={"name": "MyToken", "token_type": "url"})
    token_id = create.json()["id"]
    r = await client.get(f"/api/tokens/{token_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "MyToken"


@pytest.mark.asyncio
async def test_delete_token(client):
    create = await client.post("/api/tokens/", json={"name": "Del", "token_type": "url"})
    token_id = create.json()["id"]
    r = await client.delete(f"/api/tokens/{token_id}")
    assert r.status_code == 200
    r2 = await client.get(f"/api/tokens/{token_id}")
    assert r2.status_code == 404


# ── Capture (trigger) pipeline ───────────────────────────────────

@pytest.mark.asyncio
async def test_url_token_trigger(client):
    """Hitting the capture URL increments trigger count and creates a Trigger record."""
    create = await client.post("/api/tokens/", json={"name": "URL Canary", "token_type": "url"})
    token_id = create.json()["id"]

    # Extract slug from token_value
    token_value = create.json()["token_value"]
    # e.g. http://testserver/c/u/<token_id>/<slug>
    path = "/" + "/".join(token_value.split("/")[3:])

    r = await client.get(path, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124"})
    assert r.status_code == 204

    # Check trigger_count incremented
    token = await client.get(f"/api/tokens/{token_id}")
    assert token.json()["trigger_count"] == 1

    # Check trigger was logged
    triggers = await client.get(f"/api/alerts/?token_id={token_id}")
    assert len(triggers.json()) == 1
    t = triggers.json()[0]
    assert t["token_type"] == "url"
    assert t["risk_score"] >= 0


@pytest.mark.asyncio
async def test_email_pixel_returns_gif(client):
    """Email pixel endpoint returns a transparent GIF."""
    create = await client.post("/api/tokens/", json={"name": "Email Pixel", "token_type": "email"})
    token_value = create.json()["token_value"]
    path = "/" + "/".join(token_value.split("/")[3:])

    r = await client.get(path)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/gif"
    assert r.content[:6] == b"GIF89a"


@pytest.mark.asyncio
async def test_multiple_triggers_accumulate(client):
    create = await client.post("/api/tokens/", json={"name": "Multi", "token_type": "url"})
    token_id = create.json()["id"]
    path = "/" + "/".join(create.json()["token_value"].split("/")[3:])

    for _ in range(3):
        await client.get(path)

    token = await client.get(f"/api/tokens/{token_id}")
    assert token.json()["trigger_count"] == 3

    triggers = await client.get(f"/api/alerts/?token_id={token_id}")
    assert len(triggers.json()) == 3


# ── Scoring engine (unit tests) ───────────────────────────────────

def test_score_browser_ua():
    from backend.scoring.engine import score_trigger
    result = score_trigger(
        ip_address="1.2.3.4",
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/124",
        referer=None, headers={},
        geo_country="US", token_type="url"
    )
    assert result.total > 20
    assert result.recommendation in ("alert", "monitor")
    assert "browser_user_agent" in result.breakdown


def test_score_bot_ua_suppressed():
    from backend.scoring.engine import score_trigger
    result = score_trigger(
        ip_address="1.2.3.4",
        user_agent="python-requests/2.31.0",
        referer=None, headers={},
        geo_country="US", token_type="url"
    )
    assert result.recommendation == "suppress"
    assert result.is_false_positive is True


def test_score_aws_token_boost():
    from backend.scoring.engine import score_trigger
    result = score_trigger(
        ip_address="5.6.7.8",
        user_agent="aws-sdk-java/1.12",
        referer=None, headers={},
        geo_country="RU", token_type="aws"
    )
    # AWS use from high-risk country should score high
    assert result.total >= 40
    assert "aws_token_multiplier" in result.breakdown
    assert "high_risk_country" in result.breakdown


def test_score_no_user_agent():
    from backend.scoring.engine import score_trigger
    result = score_trigger(
        ip_address="1.2.3.4",
        user_agent="",
        referer=None, headers={},
        geo_country=None, token_type="url"
    )
    assert "no_user_agent" in result.breakdown


def test_score_allowlisted_ip_suppressed(monkeypatch):
    from backend.scoring import engine
    monkeypatch.setattr(engine.settings, "ALLOWLISTED_IPS", ["203.0.113.5"])
    result = engine.score_trigger(
        ip_address="203.0.113.5",
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/124",
        referer=None, headers={},
        geo_country="RU", token_type="aws"
    )
    assert result.total == 0.0
    assert result.recommendation == "suppress"
    assert result.is_false_positive is True


def test_score_allowlisted_cidr_range(monkeypatch):
    from backend.scoring import engine
    monkeypatch.setattr(engine.settings, "ALLOWLISTED_IPS", ["198.51.100.0/24"])
    result = engine.score_trigger(
        ip_address="198.51.100.42",
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/124",
        referer=None, headers={},
        geo_country="US", token_type="url"
    )
    assert result.recommendation == "suppress"


def test_score_non_allowlisted_ip_scores_normally(monkeypatch):
    from backend.scoring import engine
    monkeypatch.setattr(engine.settings, "ALLOWLISTED_IPS", ["203.0.113.5"])
    result = engine.score_trigger(
        ip_address="8.8.8.8",
        user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/124",
        referer=None, headers={},
        geo_country="US", token_type="url"
    )
    assert result.total > 0
    assert "allowlisted_ip" not in result.breakdown


# ── Dashboard stats ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_stats_empty(client):
    r = await client.get("/api/dashboard/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_tokens"] == 0
    assert data["total_triggers"] == 0


@pytest.mark.asyncio
async def test_dashboard_stats_after_activity(client):
    await client.post("/api/tokens/", json={"name": "T1", "token_type": "url"})
    create2 = await client.post("/api/tokens/", json={"name": "T2", "token_type": "email"})
    path = "/" + "/".join(create2.json()["token_value"].split("/")[3:])
    await client.get(path)

    r = await client.get("/api/dashboard/stats")
    data = r.json()
    assert data["total_tokens"] == 2
    assert data["total_triggers"] == 1


# ── Alerts filtering ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alerts_filter_by_token(client):
    c1 = await client.post("/api/tokens/", json={"name": "T1", "token_type": "url"})
    c2 = await client.post("/api/tokens/", json={"name": "T2", "token_type": "url"})

    path1 = "/" + "/".join(c1.json()["token_value"].split("/")[3:])
    path2 = "/" + "/".join(c2.json()["token_value"].split("/")[3:])

    await client.get(path1)
    await client.get(path2)
    await client.get(path2)

    r1 = await client.get(f"/api/alerts/?token_id={c1.json()['id']}")
    r2 = await client.get(f"/api/alerts/?token_id={c2.json()['id']}")

    assert len(r1.json()) == 1
    assert len(r2.json()) == 2