"""
Smart reprocessing system for validation failures
"""
import logging
from typing import Dict, Any, Optional, List
from PIL import Image

from .validators import validate_extracted_data, validate_address_format
from .vision import vision_model

logger = logging.getLogger(__name__)


class ReprocessingStrategy:
    """Strategy for reprocessing based on validation failure types"""

    def __init__(self):
        self.max_retries = 2
        self.retry_strategies = {
            "address_format": self._enhance_address_prompt,
            "service_provider_structure": self._enhance_structure_prompt,
            "amount_format": self._enhance_amount_prompt,
            "general": self._enhance_general_prompt
        }

    def should_retry(self, validation_result: Dict[str, Any]) -> bool:
        """Determine if we should retry based on validation errors"""
        if validation_result["is_valid"]:
            return False

        errors = validation_result.get("validation_errors", [])

        # Don't retry if no specific errors to fix
        if not errors:
            return False

        # Check for retryable error types
        retryable_errors = [
            "address format",
            "service_provider",
            "Amount must be a valid number",
            "too short",
            "missing"
        ]

        return any(
            any(keyword in error.lower() for keyword in retryable_errors)
            for error in errors
        )

    def classify_errors(self, validation_errors: List[str]) -> str:
        """Classify the primary error type for targeted retry strategy"""
        error_text = " ".join(validation_errors).lower()

        if "address" in error_text and ("comma" in error_text or "format" in error_text):
            return "address_format"
        elif "service_provider" in error_text:
            return "service_provider_structure"
        elif "amount" in error_text:
            return "amount_format"
        else:
            return "general"

    def _enhance_address_prompt(self, original_prompt: str, errors: List[str]) -> str:
        """Enhance prompt to better extract address information"""
        address_enhancement = """

CRITICAL ADDRESS FORMATTING REQUIREMENTS:
- The address MUST be a complete address with street, city, postal code, and country
- Format EXACTLY as: "Street Number Street Name, City Postal Code, Country"
- Example: "Sarló u 7, Székesfehérvár 8000, Hungary"
- DO NOT use partial addresses, abbreviations, or incomplete information
- If you can see any part of an address on the document, extract ALL visible components
- Look carefully for street numbers, street names, city names, postal codes, and country information
- Combine all address components into a single complete string

POSITIVE ADDRESS EXAMPLES (CORRECT formats to follow):

{
  "service_provider": {
    "name": "Magyar Solutions Kft",
    "address": "Váci út 1-3, Budapest 1052, Hungary"
  }
}

{
  "service_provider": {
    "name": "Berlin Tech GmbH",
    "address": "Unter den Linden 42, Berlin 10117, Germany"
  }
}

{
  "service_provider": {
    "name": "NYC Services Inc",
    "address": "123 Business Street, New York, NY 10001, United States"
  }
}

NEGATIVE ADDRESS EXAMPLES (INCORRECT - DO NOT DO THIS):

"Budapest" (too short, missing street and postal code)
"Main Street 123, Berlin 10117" (missing country)
"Main Street 123 Berlin Germany" (missing commas)
"Address not available" (placeholder text)
Just company name without address

COMMON ADDRESS EXTRACTION MISTAKES TO AVOID:
- DO NOT return just the company name without address
- DO NOT return partial addresses like "Budapest" or "Main Street"
- DO NOT use placeholders like "Address not provided"
- DO NOT split address into multiple fields - combine into ONE string
- DO NOT forget commas between address components
- DO NOT omit country information from the address

If you cannot find a complete address with at least street, city, and country components,
look more carefully at the entire document including headers, footers, and contact information sections.
        """

        return original_prompt + address_enhancement

    def _enhance_structure_prompt(self, original_prompt: str, errors: List[str]) -> str:
        """Enhance prompt to ensure proper JSON structure"""
        structure_enhancement = """

CRITICAL JSON STRUCTURE REQUIREMENTS:
- service_provider MUST be an object (not a string) with "name" and "address" fields
- NEVER return service_provider as a simple string
- Use service_provider for ALL types of providers (stores, restaurants, companies, etc.)

CORRECT FORMAT EXAMPLES:

For invoices and receipts (service_provider):
{
  "service_provider": {
    "name": "Tech Solutions Kft",
    "address": "Sarló u 7, Székesfehérvár 8000, Hungary"
  }
}

For stores/restaurants (service_provider):
{
  "service_provider": {
    "name": "Café Central",
    "address": "Herrengasse 14, Wien 1010, Austria"
  }
}

INCORRECT FORMAT EXAMPLES (DO NOT DO THIS):

{
  "service_provider": "Just company name"  // WRONG! Must be object
}

{
  "service_provider": "Store Name Only"  // WRONG! Must be object
}

{
  "service_provider": {
    "name": "Company Name"
    // WRONG! Missing address field
  }
}

VERIFICATION CHECKLIST:
- Is service_provider an object with both "name" and "address"?
- Does the address follow the complete format with street, city, country?
- Is the JSON syntax valid (proper commas, brackets, quotes)?

Double-check your JSON structure before returning the response.
        """

        return original_prompt + structure_enhancement

    def _enhance_amount_prompt(self, original_prompt: str, errors: List[str]) -> str:
        """Enhance prompt to better extract numeric amounts"""
        amount_enhancement = """

CRITICAL AMOUNT EXTRACTION REQUIREMENTS:
- amount MUST be a numeric value (not text)
- Look for the total amount, final amount, or amount due
- Remove currency symbols, commas, and spaces
- Convert to decimal format (e.g., 1500.50)
- If you see "1,500.50 EUR", return just 1500.50 as the amount

EXAMPLES:
- "€1,500.50" → amount: 1500.50
- "$1000" → amount: 1000.00
- "2.500,75 HUF" → amount: 2500.75

Extract ONLY the numeric value without any text or symbols.
        """

        return original_prompt + amount_enhancement

    def _enhance_general_prompt(self, original_prompt: str, errors: List[str]) -> str:
        """General prompt enhancement for better extraction accuracy"""
        general_enhancement = """

CRITICAL DATA EXTRACTION REQUIREMENTS:
- Read the document VERY carefully and extract ALL visible information
- Pay special attention to addresses, company names, and amounts
- Look in headers, footers, contact sections, and invoice details
- Ensure ALL required fields are filled with actual data from the document
- Double-check that your extracted data matches what you see in the image

If any field seems incomplete, look again at the entire document more carefully.
        """

        return original_prompt + general_enhancement


async def reprocess_with_enhanced_prompt(
    image: Image.Image,
    original_system_prompt: str,
    original_user_prompt: str,
    validation_result: Dict[str, Any],
    retry_count: int = 1
) -> Dict[str, Any]:
    """
    Reprocess document with enhanced prompt based on validation failures

    Args:
        image: PIL Image to reprocess
        original_system_prompt: Original system prompt
        original_user_prompt: Original user prompt
        validation_result: Result from failed validation
        retry_count: Current retry attempt number

    Returns:
        New processing result dictionary
    """
    strategy = ReprocessingStrategy()

    if not strategy.should_retry(validation_result):
        logger.info("Validation errors not suitable for retry")
        return {
            "success": False,
            "data": None,
            "error": "Validation failed and automatic retry not applicable",
            "retry_attempted": False,
            "original_errors": validation_result.get("validation_errors", [])
        }

    # Classify error type and get appropriate enhancement
    error_type = strategy.classify_errors(validation_result.get("validation_errors", []))
    enhance_func = strategy.retry_strategies[error_type]

    logger.info(f"Reprocessing attempt {retry_count} with strategy: {error_type}")

    # Create enhanced prompts
    enhanced_system_prompt = original_system_prompt + f"\n\nRETRY ATTEMPT {retry_count}: Previous extraction had validation errors. Please extract more carefully."
    enhanced_user_prompt = enhance_func(original_user_prompt, validation_result.get("validation_errors", []))

    try:
        # Reprocess with enhanced prompts
        result = vision_model.analyze_image(
            image=image,
            system_prompt=enhanced_system_prompt,
            user_prompt=enhanced_user_prompt,
            temperature=0.05,  # Lower temperature for more deterministic results
            max_tokens=2500   # More tokens for detailed extraction
        )

        if result["success"] and result.get("data"):
            # Validate the reprocessed data
            new_validation = validate_extracted_data(result["data"])

            if new_validation["is_valid"]:
                logger.info(f"Reprocessing successful on attempt {retry_count}")
                result["data"] = new_validation["corrected_data"]
                result["retry_succeeded"] = True
                result["retry_attempt"] = retry_count
                result["retry_strategy"] = error_type
                result["original_errors"] = validation_result.get("validation_errors", [])

                if new_validation.get("validation_warnings"):
                    result["retry_warnings"] = new_validation["validation_warnings"]

                return result
            else:
                logger.warning(f"Reprocessing attempt {retry_count} still has validation errors: {new_validation['validation_errors']}")

                # Try one more time if we haven't reached max retries
                if retry_count < strategy.max_retries:
                    return await reprocess_with_enhanced_prompt(
                        image=image,
                        original_system_prompt=original_system_prompt,
                        original_user_prompt=original_user_prompt,
                        validation_result=new_validation,
                        retry_count=retry_count + 1
                    )
                else:
                    result["retry_succeeded"] = False
                    result["retry_attempt"] = retry_count
                    result["retry_strategy"] = error_type
                    result["final_validation_errors"] = new_validation["validation_errors"]
                    result["original_errors"] = validation_result.get("validation_errors", [])
                    return result
        else:
            logger.error(f"Reprocessing attempt {retry_count} failed: {result.get('error')}")
            return {
                "success": False,
                "data": None,
                "error": f"Reprocessing attempt {retry_count} failed: {result.get('error')}",
                "retry_succeeded": False,
                "retry_attempt": retry_count,
                "retry_strategy": error_type,
                "original_errors": validation_result.get("validation_errors", [])
            }

    except Exception as e:
        logger.error(f"Error during reprocessing attempt {retry_count}: {e}")
        return {
            "success": False,
            "data": None,
            "error": f"Reprocessing failed: {str(e)}",
            "retry_succeeded": False,
            "retry_attempt": retry_count,
            "retry_strategy": error_type,
            "original_errors": validation_result.get("validation_errors", [])
        }


async def reprocess_multiple_pages(
    images: List[Image.Image],
    original_system_prompt: str,
    original_user_prompt: str,
    validation_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Reprocess multiple pages (e.g., from PDF) with enhanced prompts

    Args:
        images: List of PIL Images to reprocess
        original_system_prompt: Original system prompt
        original_user_prompt: Original user prompt
        validation_result: Result from failed validation

    Returns:
        List of processing result dictionaries
    """
    results = []

    for i, image in enumerate(images):
        logger.info(f"Reprocessing page {i+1}/{len(images)}")

        result = await reprocess_with_enhanced_prompt(
            image=image,
            original_system_prompt=original_system_prompt,
            original_user_prompt=original_user_prompt,
            validation_result=validation_result
        )

        results.append(result)

        # If we found a successful result, we can stop
        if result.get("success") and result.get("retry_succeeded"):
            logger.info(f"Successful reprocessing found on page {i+1}")
            break

    return results


def create_reprocessing_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of the reprocessing attempt

    Args:
        result: Processing result with retry information

    Returns:
        Summary dictionary
    """
    summary = {
        "reprocessing_attempted": result.get("retry_attempt", 0) > 0,
        "reprocessing_successful": result.get("retry_succeeded", False),
        "retry_attempts": result.get("retry_attempt", 0),
        "strategy_used": result.get("retry_strategy"),
        "original_errors": result.get("original_errors", []),
        "final_status": "success" if result.get("retry_succeeded") else "failed"
    }

    if result.get("retry_succeeded"):
        summary["improvements_made"] = "Validation issues resolved through enhanced prompting"
        if result.get("retry_warnings"):
            summary["remaining_warnings"] = result["retry_warnings"]
    else:
        summary["final_errors"] = result.get("final_validation_errors", [])
        summary["recommendation"] = "Manual review recommended - automatic reprocessing could not resolve validation issues"

    return summary