"""
FastAPI application for invoice/receipt processing with vLLM vision models
"""
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from .config import config
from .models import (
    ProcessResponse,
    HealthResponse,
    TemplateInfo,
    TokenCostsResponse,
    TokenUsageRecord,
    TokenUsageStats,
    ProviderStats
)
from .vision import vision_model
from .utils import (
    pdf_bytes_to_images,
    bytes_to_image,
    validate_file_extension
)
from .database import init_db, get_session, TokenUsage
from .token_service import (
    save_token_usage,
    get_token_usage_history,
    get_token_usage_stats,
    get_token_usage_by_provider,
    fetch_openrouter_pricing
)
from .validators import (
    validate_extracted_data,
    format_validation_response
)
from .reprocessing import (
    reprocess_with_enhanced_prompt,
    reprocess_multiple_pages,
    create_reprocessing_summary
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Bookkeeping Automation API",
    description="API for processing invoices and receipts using vision models",
    version="1.0.0",
    root_path="/api",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and fetch pricing on startup"""
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully")

    # Fetch OpenRouter pricing at startup if using OpenRouter provider
    if config.provider == "openrouter":
        logger.info("Fetching OpenRouter pricing at startup...")
        try:
            pricing_map = await fetch_openrouter_pricing()
            if pricing_map:
                logger.info(f"Successfully loaded pricing for {len(pricing_map)} models")
            else:
                logger.warning("No pricing data fetched, will use fallback pricing")
        except Exception as e:
            logger.error(f"Failed to fetch pricing at startup: {e}. Will use fallback pricing.")
    else:
        logger.info(f"Using {config.provider} provider - no pricing fetch needed")


@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Bookkeeping Automation API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "process": "/process (POST)",
            "templates": "/templates",
            "reload_config": "/reload-config (POST)",
            "token_costs": "/token-costs"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        available_templates = list(config.get_available_templates().keys())
        return HealthResponse(
            status="healthy",
            model_loaded=True,
            available_templates=available_templates,
            provider=config.provider,
            model_name=vision_model.model_name
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            model_loaded=False,
            available_templates=[],
            provider=config.provider,
            model_name=None
        )


@app.get("/templates", response_model=dict)
async def list_templates():
    """List available prompt templates"""
    templates = config.get_available_templates()
    return {
        "templates": [
            {"name": name, "description": desc}
            for name, desc in templates.items()
        ]
    }


@app.post("/reload-config")
async def reload_config():
    """Reload configuration from file (useful for updating prompts without restart)"""
    try:
        config.reload_prompts()
        return {"message": "Configuration reloaded successfully"}
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload config: {str(e)}")


@app.post("/validate-data")
async def validate_data_endpoint(data: Dict[str, Any]):
    """
    Validate extracted data format independently

    This endpoint allows you to validate data format without processing a document.
    Useful for testing and ensuring data consistency.

    Args:
        data: The extracted data dictionary to validate

    Returns:
        Validation result with corrected data and validation messages
    """
    try:
        validation_result = validate_extracted_data(data)
        return format_validation_response(validation_result)
    except Exception as e:
        logger.error(f"Error validating data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")


@app.post("/reprocess")
async def reprocess_document(
    file: UploadFile = File(..., description="Image or PDF file to reprocess"),
    buyer: Optional[str] = Form(None, description="Name of the buyer (optional)"),
    template: str = Form("default_invoice", description="Prompt template to use"),
    force_retry: bool = Form(False, description="Force reprocessing even if initial processing succeeds"),
    session: AsyncSession = Depends(get_session)
):
    """
    Reprocess a document with enhanced validation and automatic retry logic

    This endpoint processes a document and automatically attempts reprocessing
    with enhanced prompts if validation fails. It provides detailed information
    about the reprocessing attempts and their outcomes.

    Args:
        file: The uploaded file (image or PDF)
        buyer: Optional buyer name to help identify the service provider
        template: Name of the prompt template to use
        force_retry: If True, will attempt reprocessing even if initial processing succeeds
        session: Database session

    Returns:
        ProcessResponse with detailed reprocessing information
    """
    try:
        # Validate file extension
        if not validate_file_extension(file.filename, config.allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {config.allowed_extensions}"
            )

        # Read file content
        file_content = await file.read()

        # Check file size
        if len(file_content) > config.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {config.max_file_size / (1024*1024)}MB"
            )

        # Get prompt template
        try:
            prompt_template = config.get_prompt_template(template)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Build prompts
        current_date = datetime.now()
        current_year = current_date.year
        current_date_str = current_date.strftime("%Y-%m-%d")

        system_prompt = prompt_template["system_prompt"]
        date_context = f"\n\nCurrent date: {current_date_str}. When inferring dates without explicit years, assume the current year {current_year} unless context suggests otherwise."
        system_prompt = system_prompt + date_context

        user_prompt = prompt_template["user_prompt"]

        if buyer:
            buyer_context = f"Note: The buyer/customer for this invoice is: {buyer}"
        else:
            buyer_context = ""

        user_prompt = user_prompt.format(buyer_context=buyer_context)

        # Process based on file type
        file_ext = Path(file.filename).suffix.lower()

        if file_ext == ".pdf":
            logger.info(f"Reprocessing PDF: {file.filename}")
            images = pdf_bytes_to_images(file_content)

            # Try initial processing
            results = vision_model.analyze_images(
                images=images,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            for result in results:
                if result["success"]:
                    # Validate initial result
                    validation_result = validate_extracted_data(result["data"]) if result.get("data") else {"is_valid": False}

                    if not validation_result["is_valid"] or force_retry:
                        logger.info(f"Attempting reprocessing (force_retry={force_retry})")

                        # Attempt reprocessing
                        reprocess_results = await reprocess_multiple_pages(
                            images=images,
                            original_system_prompt=system_prompt,
                            original_user_prompt=user_prompt,
                            validation_result=validation_result
                        )

                        # Find best result
                        for reprocess_result in reprocess_results:
                            if reprocess_result.get("retry_succeeded"):
                                result = reprocess_result
                                break
                        else:
                            # Add reprocessing summary to original result
                            result["reprocessing_summary"] = create_reprocessing_summary(
                                reprocess_results[-1] if reprocess_results else {}
                            )
                    else:
                        # Initial processing was successful
                        result["data"] = validation_result["corrected_data"]
                        result["reprocessing_summary"] = {"reprocessing_attempted": False, "reason": "initial_validation_passed"}

                    return ProcessResponse(**result)

            # No successful result
            return ProcessResponse(
                success=False,
                data=None,
                error="No page could be processed successfully",
                reprocessing_summary={"reprocessing_attempted": True, "final_status": "failed"}
            )

        else:
            # Process single image
            logger.info(f"Reprocessing image: {file.filename}")
            image = bytes_to_image(file_content)

            # Try initial processing
            result = vision_model.analyze_image(
                image=image,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            if result["success"]:
                # Validate initial result
                validation_result = validate_extracted_data(result["data"]) if result.get("data") else {"is_valid": False}

                if not validation_result["is_valid"] or force_retry:
                    logger.info(f"Attempting reprocessing (force_retry={force_retry})")

                    # Attempt reprocessing
                    reprocess_result = await reprocess_with_enhanced_prompt(
                        image=image,
                        original_system_prompt=system_prompt,
                        original_user_prompt=user_prompt,
                        validation_result=validation_result
                    )

                    if reprocess_result.get("retry_succeeded"):
                        result = reprocess_result
                    else:
                        result["reprocessing_summary"] = create_reprocessing_summary(reprocess_result)
                else:
                    # Initial processing was successful
                    result["data"] = validation_result["corrected_data"]
                    result["reprocessing_summary"] = {"reprocessing_attempted": False, "reason": "initial_validation_passed"}

            return ProcessResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during reprocessing: {e}", exc_info=True)
        return ProcessResponse(
            success=False,
            data=None,
            error=str(e),
            reprocessing_summary={"reprocessing_attempted": True, "final_status": "error", "error": str(e)}
        )


@app.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(..., description="Image or PDF file to process"),
    buyer: Optional[str] = Form(None, description="Name of the buyer (optional)"),
    template: str = Form("default_invoice", description="Prompt template to use"),
    session: AsyncSession = Depends(get_session)
):
    """
    Process an uploaded image or PDF document

    Args:
        file: The uploaded file (image or PDF)
        buyer: Optional buyer name to help identify the service provider
        template: Name of the prompt template to use (default: default_invoice)

    Returns:
        ProcessResponse with extracted data in JSON format
    """
    try:
        # Validate file extension
        if not validate_file_extension(file.filename, config.allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {config.allowed_extensions}"
            )

        # Read file content
        file_content = await file.read()

        # Check file size
        if len(file_content) > config.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {config.max_file_size / (1024*1024)}MB"
            )

        # Get prompt template
        try:
            prompt_template = config.get_prompt_template(template)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Get current date for context
        current_date = datetime.now()
        current_year = current_date.year
        current_date_str = current_date.strftime("%Y-%m-%d")

        # Build system prompt with date context
        system_prompt = prompt_template["system_prompt"]
        date_context = f"\n\nCurrent date: {current_date_str}. When inferring dates without explicit years, assume the current year {current_year} unless context suggests otherwise. For partial dates (like 'Jan 15' or '1/15'), default to {current_year}."
        system_prompt = system_prompt + date_context

        user_prompt = prompt_template["user_prompt"]

        # Add buyer context if provided
        if buyer:
            buyer_context = f"Note: The buyer/customer for this invoice is: {buyer}"
        else:
            buyer_context = ""

        user_prompt = user_prompt.format(buyer_context=buyer_context)

        # Process based on file type
        file_ext = Path(file.filename).suffix.lower()

        if file_ext == ".pdf":
            logger.info(f"Processing PDF: {file.filename}")
            # Convert PDF to images
            images = pdf_bytes_to_images(file_content)
            logger.info(f"PDF has {len(images)} page(s)")

            # Process all pages
            results = vision_model.analyze_images(
                images=images,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            # For multi-page PDFs, return the first successful result
            # or all results if you want to handle multi-page invoices
            for i, result in enumerate(results):
                if result["success"]:
                    logger.info(f"Successfully processed page {i+1}")

                    # Validate and format the extracted data
                    if result.get("data"):
                        validation_result = validate_extracted_data(result["data"])
                        if validation_result["is_valid"]:
                            # Use corrected data
                            result["data"] = validation_result["corrected_data"]
                            if validation_result["validation_warnings"]:
                                logger.info(f"Validation warnings: {validation_result['validation_warnings']}")
                        else:
                            # Log validation failures but do not trigger automatic reprocessing
                            logger.error(f"Data validation failed: {validation_result['validation_errors']}")
                            result["validation_errors"] = validation_result["validation_errors"]
                            result["validation_warnings"] = validation_result["validation_warnings"]
                            # Note: Automatic reprocessing disabled - validation results logged only

                    # Save token usage to database
                    token_usage = result.get("token_usage")
                    if token_usage:
                        await save_token_usage(
                            session=session,
                            filename=file.filename,
                            buyer=buyer,
                            template=template,
                            provider=config.provider,
                            model_name=vision_model.model_name,
                            prompt_tokens=token_usage.get("prompt_tokens"),
                            completion_tokens=token_usage.get("completion_tokens"),
                            total_tokens=token_usage.get("total_tokens"),
                            num_images=len(images),
                            success=True,
                            error_message=None
                        )

                    return ProcessResponse(**result)

            # If no page was successful, return the last result
            last_result = results[-1]

            # Save token usage for failed request
            token_usage = last_result.get("token_usage")
            if token_usage:
                await save_token_usage(
                    session=session,
                    filename=file.filename,
                    buyer=buyer,
                    template=template,
                    provider=config.provider,
                    model_name=vision_model.model_name,
                    prompt_tokens=token_usage.get("prompt_tokens"),
                    completion_tokens=token_usage.get("completion_tokens"),
                    total_tokens=token_usage.get("total_tokens"),
                    num_images=len(images),
                    success=False,
                    error_message=last_result.get("error")
                )

            return ProcessResponse(**last_result)

        else:
            # Process as image
            logger.info(f"Processing image: {file.filename}")
            image = bytes_to_image(file_content)

            result = vision_model.analyze_image(
                image=image,
                system_prompt=system_prompt,
                user_prompt=user_prompt
            )

            # Validate and format the extracted data
            if result["success"] and result.get("data"):
                validation_result = validate_extracted_data(result["data"])
                if validation_result["is_valid"]:
                    # Use corrected data
                    result["data"] = validation_result["corrected_data"]
                    if validation_result["validation_warnings"]:
                        logger.info(f"Validation warnings: {validation_result['validation_warnings']}")
                else:
                    # Log validation failures but do not trigger automatic reprocessing
                    logger.error(f"Data validation failed: {validation_result['validation_errors']}")
                    result["validation_errors"] = validation_result["validation_errors"]
                    result["validation_warnings"] = validation_result["validation_warnings"]
                    # Note: Automatic reprocessing disabled - validation results logged only

            # Save token usage to database
            token_usage = result.get("token_usage")
            if token_usage:
                await save_token_usage(
                    session=session,
                    filename=file.filename,
                    buyer=buyer,
                    template=template,
                    provider=config.provider,
                    model_name=vision_model.model_name,
                    prompt_tokens=token_usage.get("prompt_tokens"),
                    completion_tokens=token_usage.get("completion_tokens"),
                    total_tokens=token_usage.get("total_tokens"),
                    num_images=1,
                    success=result["success"],
                    error_message=result.get("error")
                )

            return ProcessResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        return ProcessResponse(
            success=False,
            data=None,
            error=str(e),
            raw_response=None
        )


@app.get("/token-costs", response_model=TokenCostsResponse)
async def get_token_costs(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    provider: Optional[str] = Query(None, description="Filter by provider (openrouter or vllm)"),
    buyer: Optional[str] = Query(None, description="Filter by buyer name"),
    start_date: Optional[datetime] = Query(None, description="Filter records after this date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter records before this date (ISO format)"),
    session: AsyncSession = Depends(get_session)
):
    """
    Get historical token usage and costs for all processed documents.

    This endpoint returns:
    - Individual token usage records with costs
    - Aggregated statistics (total tokens, costs, requests)
    - Provider breakdown (costs per provider)

    Query parameters allow filtering by:
    - Date range
    - Provider (openrouter or vllm)
    - Buyer name
    - Pagination (limit/offset)

    Example:
        GET /token-costs?limit=50&provider=openrouter&start_date=2024-01-01T00:00:00
    """
    try:
        # Get filtered records
        records = await get_token_usage_history(
            session=session,
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            provider=provider,
            buyer=buyer
        )

        # Get aggregated stats
        stats = await get_token_usage_stats(
            session=session,
            start_date=start_date,
            end_date=end_date
        )

        # Get provider breakdown
        provider_breakdown = await get_token_usage_by_provider(
            session=session,
            start_date=start_date,
            end_date=end_date
        )

        # Get total count for pagination
        count_query = select(func.count(TokenUsage.id))
        if start_date:
            count_query = count_query.where(TokenUsage.timestamp >= start_date)
        if end_date:
            count_query = count_query.where(TokenUsage.timestamp <= end_date)
        if provider:
            count_query = count_query.where(TokenUsage.provider == provider)
        if buyer:
            count_query = count_query.where(TokenUsage.buyer == buyer)

        result = await session.execute(count_query)
        total_count = result.scalar()

        # Convert records to Pydantic models
        record_models = [
            TokenUsageRecord(
                id=r.id,
                timestamp=r.timestamp,
                filename=r.filename,
                buyer=r.buyer,
                template=r.template,
                provider=r.provider,
                model_name=r.model_name,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                prompt_cost=r.prompt_cost,
                completion_cost=r.completion_cost,
                total_cost=r.total_cost,
                success=bool(r.success),
                error_message=r.error_message,
                num_images=r.num_images
            )
            for r in records
        ]

        return TokenCostsResponse(
            records=record_models,
            stats=TokenUsageStats(**stats),
            provider_breakdown=[ProviderStats(**p) for p in provider_breakdown],
            total_records=total_count or 0,
            limit=limit,
            offset=offset
        )

    except Exception as e:
        logger.error(f"Error retrieving token costs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve token costs: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
