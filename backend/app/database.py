"""Database configuration and models for token usage tracking."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, Text, create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database URL - using SQLite for simplicity
DATABASE_URL = "sqlite+aiosqlite:///./token_usage.db"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False}
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


class TokenUsage(Base):
    """Model for tracking token usage and costs per API call."""

    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Request details
    filename = Column(String(255), nullable=True)
    buyer = Column(String(255), nullable=True)
    template = Column(String(100), nullable=True)

    # Provider details
    provider = Column(String(50), nullable=False)  # 'openrouter' or 'vllm'
    model_name = Column(String(100), nullable=False)

    # Token usage
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)

    # Cost calculation (USD)
    prompt_cost = Column(Float, nullable=True)
    completion_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)

    # API response details
    success = Column(Integer, nullable=False, default=1)  # 1 = success, 0 = failure
    error_message = Column(Text, nullable=True)

    # Number of images/pages processed
    num_images = Column(Integer, default=1)

    def __repr__(self):
        return (f"<TokenUsage(id={self.id}, timestamp={self.timestamp}, "
                f"model={self.model_name}, total_tokens={self.total_tokens}, "
                f"total_cost={self.total_cost})>")


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Get async database session."""
    async with async_session_maker() as session:
        yield session
