"""
PDF Canary Token — creates a .pdf file with convincing LLM-written content
and a clickable tracking link as the primary trigger.

Caveat (important, not oversold): unlike Word docs, most PDF readers do
NOT automatically fetch remote content on open — Adobe Reader and most
viewers block this by default for security reasons. The clickable link,
styled with cover text matching the document's content type, is the
reliable trigger mechanism for PDFs.
"""
import io
import secrets
from typing import Optional

from backend.config import settings
from backend.intelligence.llm_engine import get_engine, DecoyContent


async def generate_pdf_token(
    token_id: str,
    name: str,
    content_type: str = "financial",
    company_hint: Optional[str] = None,
    use_llm: bool = True,
) -> dict:
    """
    Generate a canary PDF with convincing LLM-written content.
    Primary trigger: a clickable link in the document body, with cover
    text matched to the document's content type.
    """
    slug = secrets.token_urlsafe(16)
    click_url = f"{settings.BASE_URL}/view/{slug}"

    if use_llm and settings.ANTHROPIC_API_KEY:
        engine = get_engine()
        content: DecoyContent = await engine.generate_decoy_content(
            content_type=content_type,
            company_hint=company_hint,
        )
        filename = engine.suggest_filename(content_type, content.keywords, extension="pdf")
    else:
        content = _fallback_content(content_type)
        filename = f"confidential_{content_type}_report.pdf"

    pdf_bytes = _build_pdf(content, click_url)

    return {
        "token_value": click_url,
        "slug": slug,
        "filename": filename,
        "doc_bytes": pdf_bytes,
        "metadata": {
            "name": name,
            "type": "pdf",
            "slug": slug,
            "tracking_url": click_url,
            "content_type": content_type,
            "doc_title": content.title,
            "doc_summary": content.summary,
            "link_text": content.link_text,
            "filename": filename,
            "instructions": (
                f"Drop '{filename}' in a file share or email attachment. "
                f"The document contains a '{content.link_text}' link that triggers the canary "
                f"when clicked. Note: PDF readers vary in whether they auto-fetch embedded "
                f"remote content, so the clickable link is the primary, reliable trigger — "
                f"not an automatic open-detection."
            ),
        },
    }


def _build_pdf(content: DecoyContent, click_url: str) -> bytes:
    """
    Build a .pdf file with decoy content using reportlab.
    Includes a visible link, styled with content.link_text, that triggers
    the canary when clicked or followed by automated link-scraping tooling.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DecoyTitle", parent=styles["Heading1"],
        textColor=HexColor("#1a1a2e"), fontSize=18, spaceAfter=18,
    )
    body_style = ParagraphStyle(
        "DecoyBody", parent=styles["Normal"],
        fontSize=10.5, leading=15, spaceAfter=10,
    )
    link_style = ParagraphStyle(
        "DecoyLink", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#2563eb"), spaceBefore=4,
    )

    story = [Paragraph(content.title, title_style), Spacer(1, 6)]

    for para in content.body.split("\n"):
        if para.strip():
            safe = para.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, body_style))

    story.append(Spacer(1, 20))
    # Visible, scenario-styled hyperlink — the reliable click-based trigger
    story.append(Paragraph(
        f'<link href="{click_url}">{content.link_text} &rarr;</link>',
        link_style,
    ))

    doc.build(story)
    return buf.getvalue()


def _fallback_content(content_type: str) -> DecoyContent:
    from backend.intelligence.llm_engine import DecoyContent, CONTENT_TEMPLATES

    template = CONTENT_TEMPLATES.get(content_type, CONTENT_TEMPLATES["financial"])
    return DecoyContent(
        title=f"Confidential {content_type.title()} Report — Internal Use Only",
        body=(
            "CONFIDENTIAL — DO NOT DISTRIBUTE\n\n"
            "This document contains sensitive internal information.\n"
            "Unauthorized access or distribution is prohibited."
        ),
        summary=f"Internal {content_type} document",
        keywords=[content_type, "confidential", "internal"],
        link_text=template["link_hints"][0],
    )
