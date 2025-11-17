"""
API Key authentication utilities
"""
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import config

# API Key header security
api_key_header = APIKeyHeader(
    name=config.api_key_header.upper(),
    auto_error=False
)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> bool:
    """
    Verify the provided API key

    Args:
        api_key: API key from request header

    Returns:
        bool: True if API key is valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not config.api_key:
        # If no API key is configured, allow all requests (for development)
        return True

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": f'ApiKey header="{api_key_header.name}"'},
        )

    if api_key != config.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return True


async def get_optional_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """
    Get API key from header if present, but don't require it

    Args:
        api_key: API key from request header

    Returns:
        Optional[str]: API key if provided, None otherwise
    """
    return api_key