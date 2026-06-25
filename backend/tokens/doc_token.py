"""
Document Canary Token — creates a .docx file with an embedded tracking link.
The primary, reliable trigger is a clickable link inside the document body,
styled with cover text that matches the document's content type (e.g. "View
full financial breakdown" for a financial decoy, "Open in password manager"
for a credentials decoy). Word's automatic remote-content fetch on open is
not relied upon — it's inconsistent across versions/settings and oversells
what this token can guarantee.
"""
import io
import secrets
from typing import Optional

from backend.config import settings
from backend.intelligence.llm_engine import get_engine, DecoyContent


async def generate_doc_token(
    token_id: str,
    name: str,
    content_type: str = "financial",
    company_hint: Optional[str] = None,
    use_llm: bool = True,
) -> dict:
    """
    Generate a canary document with convincing LLM-written content
    and a scenario-styled clickable tracking link as the primary trigger.
    """
    slug = secrets.token_urlsafe(16)
    click_url = f"{settings.BASE_URL}/files/{slug}"

    # Generate decoy content
    if use_llm and settings.ANTHROPIC_API_KEY:
        engine = get_engine()
        content: DecoyContent = await engine.generate_decoy_content(
            content_type=content_type,
            company_hint=company_hint,
        )
        filename = engine.suggest_filename(content_type, content.keywords)
    else:
        content = _fallback_content(content_type)
        filename = f"confidential_{content_type}_report.docx"

    doc_bytes = _build_docx(content, click_url)

    return {
        "token_value": click_url,
        "slug": slug,
        "filename": filename,
        "doc_bytes": doc_bytes,
        "metadata": {
            "name": name,
            "type": "doc",
            "slug": slug,
            "tracking_url": click_url,
            "content_type": content_type,
            "doc_title": content.title,
            "doc_summary": content.summary,
            "link_text": content.link_text,
            "filename": filename,
            "instructions": (
                f"Drop '{filename}' in a file share, email attachment, or S3 bucket. "
                f"The document contains a '{content.link_text}' link that triggers the "
                f"canary when clicked. This is the primary, reliable trigger — Word's "
                f"automatic remote-content fetch on open is not guaranteed across "
                f"versions/settings, so it is not relied on here."
            ),
        },
    }


def _build_docx(content: DecoyContent, click_url: str) -> bytes:
    """
    Build a .docx file with decoy content and a clickable hyperlink whose
    visible text matches the document's content type (content.link_text).
    Uses python-docx.
    """
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    doc = Document()

    # Title
    title_para = doc.add_heading(content.title, level=1)
    title_para.runs[0].font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)

    doc.add_paragraph()

    # Body paragraphs
    for para_text in content.body.split("\n"):
        if para_text.strip():
            doc.add_paragraph(para_text.strip())

    doc.add_paragraph()

    # Visible, scenario-styled hyperlink — the reliable trigger mechanism
    _add_hyperlink_paragraph(doc, content.link_text, click_url)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _add_hyperlink_paragraph(doc, link_text: str, url: str):
    """
    Add a paragraph containing a real, clickable hyperlink (not just
    colored text) using direct OOXML manipulation, since python-docx has
    no built-in hyperlink API. This produces a standard internal hyperlink
    relationship — the same mechanism Word uses for any normal in-document
    link — with no macros, scripts, or remote-fetch triggers involved.
    """
    part = doc.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )

    paragraph = doc.add_paragraph()
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "2563EB")
    rpr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)

    run.append(rpr)

    text_el = OxmlElement("w:t")
    text_el.text = link_text
    run.append(text_el)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


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
