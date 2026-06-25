from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Boolean, JSON, LargeBinary
from datetime import datetime, timezone
import uuid

from backend.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Token(Base):
    __tablename__ = "tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    token_type = Column(String, nullable=False)  # url, doc, email, aws, html
    token_value = Column(Text, nullable=False)    # The actual token/content
    slug = Column(String, nullable=True, index=True, unique=True)  # public-facing lookup key
    doc_bytes = Column(LargeBinary, nullable=True)  # stored .docx content for doc-type tokens
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_active = Column(Boolean, default=True)
    trigger_count = Column(Integer, default=0)


class Trigger(Base):
    __tablename__ = "triggers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_id = Column(String, nullable=False)
    token_type = Column(String, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Fingerprint data
    ip_address = Column(String)
    user_agent = Column(Text)
    referer = Column(Text)
    geo_country = Column(String)
    geo_city = Column(String)
    headers = Column(JSON, default=dict)
    extra = Column(JSON, default=dict)

    # Scoring
    risk_score = Column(Float, default=0.0)
    score_breakdown = Column(JSON, default=dict)
    is_false_positive = Column(Boolean, default=False)
    alert_fired = Column(Boolean, default=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)