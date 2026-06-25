"""
LLM Engine — Uses Claude API to generate convincing decoy document content.
This is the core intelligence layer that makes CanaryForge traps genuinely believable.
"""
import anthropic
import json
import re
from dataclasses import dataclass
from typing import Optional

from backend.config import settings


@dataclass
class DecoyContent:
    title: str
    body: str
    summary: str         # Short blurb for the token metadata
    keywords: list[str]  # For plausible filename suggestions


@dataclass
class TabularDecoyContent:
    title: str
    sheet_name: str
    headers: list[str]
    rows: list[list]      # list of row-value lists, matching headers order
    summary: str
    keywords: list[str]


SYSTEM_PROMPT = """You are a document writer for a cybersecurity red-team exercise.
Your job is to write convincing, realistic-looking internal corporate documents that would
attract an attacker's attention. These decoy documents are used as honeypot traps — they
look valuable but contain no real sensitive information.

Always respond with valid JSON only. No markdown fences, no preamble. Just JSON."""


CONTENT_TEMPLATES = {
    "financial": {
        "prompt": (
            "Write a realistic-looking internal financial document. It could be a budget memo, "
            "quarterly forecast, salary data export, or M&A due diligence note. "
            "Make it look like it was accidentally left on a file share. "
            "Use plausible but entirely fictional company names, dollar figures, and employee names."
        ),
        "filename_hints": ["Q{q}_financials", "budget_draft", "salary_bands_{year}", "acquisition_memo"],
    },
    "credentials": {
        "prompt": (
            "Write a realistic-looking internal IT document that an admin might have created — "
            "a 'passwords.txt' style note, a VPN config walkthrough, or a service account list. "
            "Include plausible but entirely fake credentials, hostnames, and IPs (use RFC 5737 ranges: 192.0.2.x). "
            "Make it look hastily written, like a real sysadmin note."
        ),
        "filename_hints": ["creds_backup", "vpn_accounts", "service_accounts", "admin_notes"],
    },
    "hr": {
        "prompt": (
            "Write a realistic internal HR document: could be a layoff list, performance review summary, "
            "org chart notes, or confidential headcount planning sheet. "
            "Use entirely fictional names and departments. Make it feel like an accidental leak."
        ),
        "filename_hints": ["headcount_{year}", "layoff_list", "perf_review_draft", "org_changes"],
    },
    "technical": {
        "prompt": (
            "Write a realistic internal technical document: could be architecture notes, "
            "a secrets management runbook, an API key rotation guide, or a production deployment checklist. "
            "Include plausible but fake infrastructure details, hostnames (use .internal or .corp domains), "
            "and fake API keys (clearly marked EXAMPLE-FAKE in the document header)."
        ),
        "filename_hints": ["infra_runbook", "deploy_checklist", "arch_notes", "secrets_rotation"],
    },
    "legal": {
        "prompt": (
            "Write a realistic internal legal or compliance document: NDA draft, "
            "data breach incident report, regulatory audit prep notes, or M&A term sheet. "
            "Use fictional company names and plausible but fake legal language."
        ),
        "filename_hints": ["nda_draft", "incident_report", "audit_prep", "term_sheet_draft"],
    },
}


# Tabular templates — for spreadsheet-shaped decoys (Excel). Each maps to a
# sheet with headers + rows rather than free-text body, since fake spreadsheets
# with one paragraph look obviously wrong.
TABULAR_TEMPLATES = {
    "financial": {
        "prompt": (
            "Generate a realistic internal financial spreadsheet — e.g. a budget breakdown, "
            "expense report, or revenue-by-department sheet. Use plausible but entirely "
            "fictional company names, department names, and dollar figures."
        ),
        "sheet_name": "Budget",
        "filename_hints": ["Q{q}_budget", "expense_report_{year}", "revenue_breakdown"],
    },
    "hr": {
        "prompt": (
            "Generate a realistic internal HR spreadsheet — e.g. a salary band sheet, "
            "headcount plan, or employee roster export. Use entirely fictional employee "
            "names, titles, and departments. Make it feel like an accidental export."
        ),
        "sheet_name": "Headcount",
        "filename_hints": ["salary_bands_{year}", "headcount_export", "employee_roster"],
    },
    "credentials": {
        "prompt": (
            "Generate a realistic internal IT spreadsheet tracking service accounts or "
            "system access — columns like system name, username, last rotated date, owner. "
            "Use fake but plausible-looking hostnames (use .internal/.corp) and fake "
            "credential references (never real-looking secrets, just labels like 'see vault')."
        ),
        "sheet_name": "Access Tracker",
        "filename_hints": ["access_tracker", "service_accounts_export", "system_inventory"],
    },
}


class LLMEngine:
    def __init__(self):
        if not settings.ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Add it to your .env file to enable "
                "LLM-generated decoy content."
            )
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def generate_decoy_content(
        self,
        content_type: str = "financial",
        company_hint: Optional[str] = None,
        extra_context: Optional[str] = None,
    ) -> DecoyContent:
        """
        Generate convincing decoy document content using Claude.

        Args:
            content_type: One of financial, credentials, hr, technical, legal
            company_hint: Optional company name to weave into the document
            extra_context: Any extra instructions to shape the content

        Returns:
            DecoyContent with title, body, summary, and filename keywords
        """
        if content_type not in CONTENT_TEMPLATES:
            content_type = "financial"

        template = CONTENT_TEMPLATES[content_type]
        company_ctx = f" The company name is '{company_hint}'." if company_hint else ""
        extra_ctx = f" Additional context: {extra_context}" if extra_context else ""

        user_prompt = f"""{template['prompt']}{company_ctx}{extra_ctx}

Respond ONLY with a JSON object in this exact shape:
{{
  "title": "Document title (as it would appear in the header)",
  "body": "Full document body text, 200-400 words, formatted with newlines for readability",
  "summary": "One sentence describing this document as if listing it in a file index",
  "keywords": ["word1", "word2", "word3"]
}}"""

        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip any accidental markdown fences
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)

        return DecoyContent(
            title=data["title"],
            body=data["body"],
            summary=data.get("summary", ""),
            keywords=data.get("keywords", []),
        )

    async def generate_tabular_content(
        self,
        content_type: str = "financial",
        company_hint: Optional[str] = None,
        extra_context: Optional[str] = None,
        num_rows: int = 12,
    ) -> TabularDecoyContent:
        """
        Generate convincing decoy spreadsheet content (headers + rows) using Claude.
        Used for Excel-type tokens, where free-text body would look out of place.

        Args:
            content_type: One of financial, hr, credentials
            company_hint: Optional company name to weave into the data
            extra_context: Any extra instructions to shape the content
            num_rows: Approximate number of data rows to generate

        Returns:
            TabularDecoyContent with title, sheet_name, headers, rows, summary, keywords
        """
        if content_type not in TABULAR_TEMPLATES:
            content_type = "financial"

        template = TABULAR_TEMPLATES[content_type]
        company_ctx = f" The company name is '{company_hint}'." if company_hint else ""
        extra_ctx = f" Additional context: {extra_context}" if extra_context else ""

        user_prompt = f"""{template['prompt']}{company_ctx}{extra_ctx}

Generate approximately {num_rows} data rows.

Respond ONLY with a JSON object in this exact shape:
{{
  "title": "Spreadsheet title (as it would appear in a header row)",
  "sheet_name": "Short sheet tab name, max 20 characters",
  "headers": ["Column1", "Column2", "Column3", "..."],
  "rows": [
    ["value1", "value2", "value3", "..."],
    ["value1", "value2", "value3", "..."]
  ],
  "summary": "One sentence describing this spreadsheet as if listing it in a file index",
  "keywords": ["word1", "word2", "word3"]
}}

Every row array must have the same number of elements as the headers array."""

        message = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = message.content[0].text.strip()
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        data = json.loads(raw)

        return TabularDecoyContent(
            title=data["title"],
            sheet_name=data.get("sheet_name", "Sheet1")[:31],  # Excel sheet name limit
            headers=data["headers"],
            rows=data["rows"],
            summary=data.get("summary", ""),
            keywords=data.get("keywords", []),
        )

    def suggest_filename(self, content_type: str, keywords: list[str], extension: str = "docx") -> str:
        """Generate a plausible filename based on content type, LLM keywords, and target extension."""
        import random
        from datetime import datetime

        # Tabular content types use TABULAR_TEMPLATES; free-text types use CONTENT_TEMPLATES
        templates = TABULAR_TEMPLATES if extension == "xlsx" else CONTENT_TEMPLATES
        template = templates.get(content_type, templates["financial"])
        base = random.choice(template["filename_hints"])

        # Fill template slots
        base = base.replace("{year}", str(datetime.now().year))
        base = base.replace("{q}", f"Q{((datetime.now().month - 1) // 3) + 1}")

        return f"{base}.{extension}"


# Module-level singleton — instantiated lazily so missing API key doesn't crash import
_engine: Optional[LLMEngine] = None


def get_engine() -> LLMEngine:
    global _engine
    if _engine is None:
        _engine = LLMEngine()
    return _engine