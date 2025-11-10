"""
Pydantic models for request/response validation
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ProcessRequest(BaseModel):
    """Request model for processing images/PDFs"""
    buyer: Optional[str] = Field(None, description="Name of the buyer/customer (optional)")
    template: str = Field("default_invoice", description="Prompt template to use")


class ProcessResponse(BaseModel):
    """Response model for processing results"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None


class TemplateInfo(BaseModel):
    """Information about a prompt template"""
    name: str
    description: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model_loaded: bool
    available_templates: List[str]
    provider: Optional[str] = None
    model_name: Optional[str] = None


class TokenUsageRecord(BaseModel):
    """Model for a single token usage record"""
    id: int
    timestamp: datetime
    filename: Optional[str] = None
    buyer: Optional[str] = None
    template: Optional[str] = None
    provider: str
    model_name: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    prompt_cost: Optional[float] = None
    completion_cost: Optional[float] = None
    total_cost: Optional[float] = None
    success: bool
    error_message: Optional[str] = None
    num_images: int = 1

    class Config:
        from_attributes = True


class TokenUsageStats(BaseModel):
    """Aggregated token usage statistics"""
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    total_images_processed: int


class ProviderStats(BaseModel):
    """Token usage statistics per provider"""
    provider: str
    total_requests: int
    total_tokens: int
    total_cost_usd: float


class TokenCostsResponse(BaseModel):
    """Response model for token costs endpoint"""
    records: List[TokenUsageRecord]
    stats: TokenUsageStats
    provider_breakdown: List[ProviderStats]
    total_records: int
    limit: int
    offset: int
