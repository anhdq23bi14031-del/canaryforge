"""
Token management API — create, list, and delete canary tokens.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional
import uuid

from backend.database import get_db, Token
from backend.tokens.url_token import generate_url_token
from backend.tokens.email_token import generate_email_token
from backend.tokens.aws_token import generate_aws_token
from backend.tokens.html_token import generate_html_token
from backend.tokens.doc_token import generate_doc_token
from backend.tokens.pdf_token import generate_pdf_token
from backend.tokens.excel_token import generate_excel_token

router = APIRouter()


class CreateTokenRequest(BaseModel):
    name: str
    token_type: str   # url | email | aws | html | doc | pdf | excel
    # Doc/PDF/Excel-specific
    content_type: Optional[str] = "financial"
    company_hint: Optional[str] = None
    use_llm: Optional[bool] = True
    # HTML-specific
    page_type: Optional[str] = "login"


@router.post("/")
async def create_token(body: CreateTokenRequest, db: AsyncSession = Depends(get_db)):
    token_id = str(uuid.uuid4())

    if body.token_type == "url":
        result = generate_url_token(token_id, body.name)
    elif body.token_type == "email":
        result = generate_email_token(token_id, body.name)
    elif body.token_type == "aws":
        result = generate_aws_token(token_id, body.name)
    elif body.token_type == "html":
        result = generate_html_token(token_id, body.name, body.page_type or "login")
    elif body.token_type == "doc":
        result = await generate_doc_token(
            token_id, body.name,
            content_type=body.content_type or "financial",
            company_hint=body.company_hint,
            use_llm=body.use_llm if body.use_llm is not None else True,
        )
    elif body.token_type == "pdf":
        result = await generate_pdf_token(
            token_id, body.name,
            content_type=body.content_type or "financial",
            company_hint=body.company_hint,
            use_llm=body.use_llm if body.use_llm is not None else True,
        )
    elif body.token_type == "excel":
        result = await generate_excel_token(
            token_id, body.name,
            content_type=body.content_type or "financial",
            company_hint=body.company_hint,
            use_llm=body.use_llm if body.use_llm is not None else True,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown token type: {body.token_type}")

    token = Token(
        id=token_id,
        name=body.name,
        token_type=body.token_type,
        token_value=result["token_value"],
        slug=result.get("slug"),
        doc_bytes=result.get("doc_bytes"),
        metadata_=result["metadata"],
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)

    response_data = {
        "id": token.id,
        "name": token.name,
        "token_type": token.token_type,
        "token_value": token.token_value,
        "metadata": token.metadata_,
        "created_at": token.created_at.isoformat(),
    }

    # For document-producing tokens, include filename hint
    if body.token_type in ("doc", "pdf", "excel") and "filename" in result:
        response_data["filename"] = result["filename"]

    return response_data


@router.get("/")
async def list_tokens(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Token).order_by(Token.created_at.desc()))
    tokens = result.scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "token_type": t.token_type,
            "token_value": t.token_value,
            "metadata": t.metadata_,
            "created_at": t.created_at.isoformat(),
            "is_active": t.is_active,
            "trigger_count": t.trigger_count,
        }
        for t in tokens
    ]


@router.get("/{token_id}")
async def get_token(token_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Token).where(Token.id == token_id))
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return {
        "id": token.id,
        "name": token.name,
        "token_type": token.token_type,
        "token_value": token.token_value,
        "metadata": token.metadata_,
        "created_at": token.created_at.isoformat(),
        "is_active": token.is_active,
        "trigger_count": token.trigger_count,
    }


@router.delete("/{token_id}")
async def delete_token(token_id: str, db: AsyncSession = Depends(get_db)):
    await db.execute(delete(Token).where(Token.id == token_id))
    await db.commit()
    return {"deleted": token_id}


DOC_MEDIA_TYPES = {
    "doc": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


@router.get("/{token_id}/download")
async def download_doc(token_id: str, db: AsyncSession = Depends(get_db)):
    """Download the originally generated file for a doc/pdf/excel token."""
    result = await db.execute(select(Token).where(Token.id == token_id))
    token = result.scalar_one_or_none()
    if not token or token.token_type not in DOC_MEDIA_TYPES:
        raise HTTPException(status_code=404, detail="Document-type token not found")

    if not token.doc_bytes:
        raise HTTPException(
            status_code=404,
            detail="No stored document found for this token. It may have been created before this feature was added.",
        )

    media_type = DOC_MEDIA_TYPES[token.token_type]
    default_ext = {"doc": "docx", "pdf": "pdf", "excel": "xlsx"}[token.token_type]
    filename = token.metadata_.get("filename", f"canary_document.{default_ext}")
    return Response(
        content=token.doc_bytes,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )