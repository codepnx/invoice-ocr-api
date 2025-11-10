"""Service layer for token usage tracking and cost calculation."""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from .database import TokenUsage

logger = logging.getLogger(__name__)

# Cache for OpenRouter pricing data
_pricing_cache: Dict[str, Any] = {}
_pricing_cache_expiry: Optional[datetime] = None
PRICING_CACHE_TTL = timedelta(hours=24)  # Cache pricing for 24 hours

# Fallback pricing per token (USD) if OpenRouter API is unavailable
FALLBACK_PRICING = {
    "openrouter": {
        "default": {
            "prompt": 0.0000002,  # $0.20 per 1M tokens
            "completion": 0.0000002  # $0.20 per 1M tokens
        }
    },
    "vllm": {
        "default": {
            "prompt": 0.0,  # Self-hosted = no per-token cost
            "completion": 0.0
        }
    }
}


async def fetch_openrouter_pricing() -> Dict[str, Dict[str, float]]:
    """
    Fetch pricing information from OpenRouter API.

    Returns:
        Dictionary mapping model names to their pricing info
    """
    global _pricing_cache, _pricing_cache_expiry

    # Check if cache is still valid
    if _pricing_cache and _pricing_cache_expiry and datetime.utcnow() < _pricing_cache_expiry:
        logger.debug("Using cached OpenRouter pricing")
        return _pricing_cache

    try:
        logger.info("Fetching pricing from OpenRouter API...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models")
            response.raise_for_status()

            models_data = response.json()
            pricing_map = {}

            # Parse pricing for each model
            for model in models_data.get("data", []):
                model_id = model.get("id")
                pricing = model.get("pricing", {})

                if model_id and pricing:
                    # OpenRouter returns pricing per token (not per million)
                    # Convert string values to float
                    pricing_map[model_id] = {
                        "prompt": float(pricing.get("prompt", "0")),
                        "completion": float(pricing.get("completion", "0"))
                    }

            # Update cache
            _pricing_cache = pricing_map
            _pricing_cache_expiry = datetime.utcnow() + PRICING_CACHE_TTL

            logger.info(f"Successfully fetched pricing for {len(pricing_map)} models from OpenRouter")
            return pricing_map

    except Exception as e:
        logger.warning(f"Failed to fetch OpenRouter pricing: {e}. Using fallback pricing.")

        # If we have cached data (even if expired), use it
        if _pricing_cache:
            logger.info("Using expired cache as fallback")
            return _pricing_cache

        # Otherwise return empty dict and rely on fallback
        return {}


async def get_model_pricing(provider: str, model_name: str) -> Dict[str, float]:
    """
    Get pricing for a specific model.

    Args:
        provider: Provider name ('openrouter' or 'vllm')
        model_name: Model identifier

    Returns:
        Dictionary with 'prompt' and 'completion' pricing per token
    """
    if provider == "vllm":
        # Self-hosted models have no per-token cost
        return {"prompt": 0.0, "completion": 0.0}

    if provider == "openrouter":
        # Fetch latest pricing from OpenRouter
        pricing_map = await fetch_openrouter_pricing()

        # Try to get pricing for specific model
        if model_name in pricing_map:
            return pricing_map[model_name]

        # Fall back to default pricing
        logger.warning(f"Pricing not found for model '{model_name}', using fallback")
        return FALLBACK_PRICING["openrouter"]["default"]

    # Unknown provider
    logger.warning(f"Unknown provider '{provider}', using zero cost")
    return {"prompt": 0.0, "completion": 0.0}


async def calculate_cost(
    provider: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int
) -> tuple[float, float, float]:
    """
    Calculate token costs based on provider and model.

    Args:
        provider: Provider name ('openrouter' or 'vllm')
        model_name: Model identifier
        prompt_tokens: Number of prompt tokens used
        completion_tokens: Number of completion tokens used

    Returns:
        Tuple of (prompt_cost, completion_cost, total_cost) in USD
    """
    pricing = await get_model_pricing(provider, model_name)

    # Pricing is per token, so multiply directly
    prompt_cost = prompt_tokens * pricing["prompt"]
    completion_cost = completion_tokens * pricing["completion"]
    total_cost = prompt_cost + completion_cost

    return prompt_cost, completion_cost, total_cost


async def save_token_usage(
    session: AsyncSession,
    filename: Optional[str],
    buyer: Optional[str],
    template: str,
    provider: str,
    model_name: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    total_tokens: Optional[int],
    num_images: int = 1,
    success: bool = True,
    error_message: Optional[str] = None
) -> TokenUsage:
    """
    Save token usage record to database.

    Args:
        session: Database session
        filename: Name of processed file
        buyer: Buyer/customer name
        template: Template used for processing
        provider: API provider ('openrouter' or 'vllm')
        model_name: Model identifier
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        total_tokens: Total tokens used
        num_images: Number of images/pages processed
        success: Whether the API call succeeded
        error_message: Error message if failed

    Returns:
        Created TokenUsage record
    """
    # Calculate costs using dynamic pricing
    prompt_cost, completion_cost, total_cost = await calculate_cost(
        provider,
        model_name,
        prompt_tokens or 0,
        completion_tokens or 0
    )

    # Create record
    usage = TokenUsage(
        timestamp=datetime.utcnow(),
        filename=filename,
        buyer=buyer,
        template=template,
        provider=provider,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_cost=prompt_cost,
        completion_cost=completion_cost,
        total_cost=total_cost,
        success=1 if success else 0,
        error_message=error_message,
        num_images=num_images
    )

    session.add(usage)
    await session.commit()
    await session.refresh(usage)

    return usage


async def get_token_usage_history(
    session: AsyncSession,
    limit: Optional[int] = 100,
    offset: int = 0,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    provider: Optional[str] = None,
    buyer: Optional[str] = None
) -> List[TokenUsage]:
    """
    Retrieve token usage history with optional filters.

    Args:
        session: Database session
        limit: Maximum number of records to return
        offset: Number of records to skip
        start_date: Filter records after this date
        end_date: Filter records before this date
        provider: Filter by provider
        buyer: Filter by buyer name

    Returns:
        List of TokenUsage records
    """
    query = select(TokenUsage).order_by(desc(TokenUsage.timestamp))

    # Apply filters
    if start_date:
        query = query.where(TokenUsage.timestamp >= start_date)
    if end_date:
        query = query.where(TokenUsage.timestamp <= end_date)
    if provider:
        query = query.where(TokenUsage.provider == provider)
    if buyer:
        query = query.where(TokenUsage.buyer == buyer)

    # Apply pagination
    if limit:
        query = query.limit(limit)
    query = query.offset(offset)

    result = await session.execute(query)
    return result.scalars().all()


async def get_token_usage_stats(
    session: AsyncSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get aggregated token usage statistics.

    Args:
        session: Database session
        start_date: Filter records after this date
        end_date: Filter records before this date

    Returns:
        Dictionary with aggregated statistics
    """
    query = select(
        func.count(TokenUsage.id).label("total_requests"),
        func.sum(TokenUsage.prompt_tokens).label("total_prompt_tokens"),
        func.sum(TokenUsage.completion_tokens).label("total_completion_tokens"),
        func.sum(TokenUsage.total_tokens).label("total_tokens"),
        func.sum(TokenUsage.total_cost).label("total_cost"),
        func.sum(TokenUsage.num_images).label("total_images"),
        func.sum(TokenUsage.success).label("successful_requests")
    )

    # Apply filters
    if start_date:
        query = query.where(TokenUsage.timestamp >= start_date)
    if end_date:
        query = query.where(TokenUsage.timestamp <= end_date)

    result = await session.execute(query)
    row = result.first()

    return {
        "total_requests": row.total_requests or 0,
        "successful_requests": row.successful_requests or 0,
        "failed_requests": (row.total_requests or 0) - (row.successful_requests or 0),
        "total_prompt_tokens": row.total_prompt_tokens or 0,
        "total_completion_tokens": row.total_completion_tokens or 0,
        "total_tokens": row.total_tokens or 0,
        "total_cost_usd": round(row.total_cost or 0, 4),
        "total_images_processed": row.total_images or 0
    }


async def get_token_usage_by_provider(
    session: AsyncSession,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Get token usage statistics grouped by provider.

    Args:
        session: Database session
        start_date: Filter records after this date
        end_date: Filter records before this date

    Returns:
        List of statistics per provider
    """
    query = select(
        TokenUsage.provider,
        func.count(TokenUsage.id).label("total_requests"),
        func.sum(TokenUsage.total_tokens).label("total_tokens"),
        func.sum(TokenUsage.total_cost).label("total_cost")
    ).group_by(TokenUsage.provider)

    # Apply filters
    if start_date:
        query = query.where(TokenUsage.timestamp >= start_date)
    if end_date:
        query = query.where(TokenUsage.timestamp <= end_date)

    result = await session.execute(query)
    rows = result.all()

    return [
        {
            "provider": row.provider,
            "total_requests": row.total_requests or 0,
            "total_tokens": row.total_tokens or 0,
            "total_cost_usd": round(row.total_cost or 0, 4)
        }
        for row in rows
    ]
