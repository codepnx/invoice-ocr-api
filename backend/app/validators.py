"""
Validation functions for ensuring correct data formatting
"""
import re
import logging
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, ValidationError, validator, Field

logger = logging.getLogger(__name__)


class AddressValidationResult(BaseModel):
    """Result of address validation"""
    is_valid: bool
    formatted_address: Optional[str] = None
    validation_errors: List[str] = []
    suggestions: List[str] = []


class ServiceProviderModel(BaseModel):
    """Validation model for service provider"""
    name: str = Field(..., min_length=1, description="Service provider name")
    address: str = Field(..., min_length=5, description="Complete address")
    tax_id: Optional[str] = Field(None, description="Tax ID")

    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Service provider name cannot be empty")
        return v.strip()

    @validator('address')
    def validate_address(cls, v):
        result = validate_address_format(v)
        if not result.is_valid:
            raise ValueError(f"Invalid address format: {', '.join(result.validation_errors)}")
        return result.formatted_address




def validate_address_format(address: str) -> AddressValidationResult:
    """
    Validate and format address to ensure it follows the required pattern:
    "Street, City PostalCode, Country" or "Street, City, PostalCode, Country"

    Args:
        address: The address string to validate

    Returns:
        AddressValidationResult with validation status and formatted address
    """
    if not address or not isinstance(address, str):
        return AddressValidationResult(
            is_valid=False,
            validation_errors=["Address cannot be empty or null"]
        )

    address = address.strip()
    if len(address) < 5:
        return AddressValidationResult(
            is_valid=False,
            validation_errors=["Address is too short (minimum 5 characters)"]
        )

    errors = []
    suggestions = []

    # Check for minimum comma count (at least 2: street, city, country)
    comma_count = address.count(',')
    if comma_count < 2:
        errors.append("Address should contain at least 2 commas separating street, city, and country")
        suggestions.append("Format should be: 'Street Address, City PostalCode, Country'")

    # Check for common formatting issues
    parts = [part.strip() for part in address.split(',')]

    if comma_count >= 2:
        # Basic structure validation
        street = parts[0] if len(parts) > 0 else ""
        city_postal = parts[1] if len(parts) > 1 else ""
        country = parts[-1] if len(parts) > 2 else ""

        # Validate street
        if not street or len(street) < 2:
            errors.append("Street address is too short or missing")

        # Validate city/postal combination
        if not city_postal or len(city_postal) < 2:
            errors.append("City and postal code section is too short or missing")

        # Check for postal code pattern in city section
        postal_pattern = r'\b\d{4,6}\b'  # 4-6 digit postal codes
        if not re.search(postal_pattern, city_postal):
            suggestions.append("Consider including postal code with city (e.g., 'Budapest 1051')")

        # Validate country
        if not country or len(country) < 2:
            errors.append("Country is missing or too short")

        # Check for suspicious patterns
        if address.lower().count('unknown') > 0:
            errors.append("Address contains 'unknown' - please provide specific location")

        if address.lower().count('n/a') > 0:
            errors.append("Address contains 'N/A' - please provide actual address")

    # Format the address consistently
    formatted_address = address
    if comma_count >= 2 and not errors:
        # Clean up spacing around commas
        formatted_parts = []
        for part in parts:
            cleaned_part = part.strip()
            # Capitalize first letter of each word (for better consistency)
            formatted_parts.append(cleaned_part)
        formatted_address = ', '.join(formatted_parts)

    is_valid = len(errors) == 0

    return AddressValidationResult(
        is_valid=is_valid,
        formatted_address=formatted_address if is_valid else None,
        validation_errors=errors,
        suggestions=suggestions
    )


def validate_extracted_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and fix common formatting issues in extracted data

    Args:
        data: The extracted data dictionary from OCR processing

    Returns:
        Dictionary with validation results and corrected data
    """
    validation_result = {
        "is_valid": True,
        "corrected_data": data.copy(),
        "validation_errors": [],
        "validation_warnings": [],
        "field_corrections": {}
    }

    try:
        # Validate service_provider field
        if "service_provider" in data:
            service_provider = data["service_provider"]

            # Handle legacy string format (auto-convert to object)
            if isinstance(service_provider, str):
                validation_result["validation_warnings"].append(
                    "service_provider was a string, converted to object format"
                )
                # Try to parse as name only
                validation_result["corrected_data"]["service_provider"] = {
                    "name": service_provider,
                    "address": "Address extraction needed"
                }
                validation_result["field_corrections"]["service_provider"] = "converted_from_string"

            # Validate object format
            elif isinstance(service_provider, dict):
                try:
                    validated_sp = ServiceProviderModel(**service_provider)
                    validation_result["corrected_data"]["service_provider"] = validated_sp.dict()
                    validation_result["field_corrections"]["service_provider"] = "validated_and_formatted"
                except ValidationError as e:
                    for error in e.errors():
                        field_path = " -> ".join(str(x) for x in error['loc'])
                        validation_result["validation_errors"].append(
                            f"service_provider.{field_path}: {error['msg']}"
                        )
                    validation_result["is_valid"] = False
            else:
                validation_result["validation_errors"].append(
                    "service_provider must be an object with name and address"
                )
                validation_result["is_valid"] = False

        # Convert legacy merchant field to service_provider
        if "merchant" in data:
            merchant = data["merchant"]
            validation_result["validation_warnings"].append(
                "merchant field found, converting to service_provider for consistency"
            )

            # Remove merchant from data and add as service_provider
            validation_result["corrected_data"].pop("merchant", None)
            validation_result["corrected_data"]["service_provider"] = merchant
            validation_result["field_corrections"]["merchant_to_service_provider"] = "converted_legacy_field"

            # Now validate the converted service_provider
            if isinstance(merchant, str):
                validation_result["validation_warnings"].append(
                    "service_provider (converted from merchant) was a string, converted to object format"
                )
                validation_result["corrected_data"]["service_provider"] = {
                    "name": merchant,
                    "address": "Address extraction needed"
                }
                validation_result["field_corrections"]["service_provider"] = "converted_from_string"

            elif isinstance(merchant, dict):
                try:
                    validated_sp = ServiceProviderModel(**merchant)
                    validation_result["corrected_data"]["service_provider"] = validated_sp.dict()
                    validation_result["field_corrections"]["service_provider"] = "validated_and_formatted"
                except ValidationError as e:
                    for error in e.errors():
                        field_path = " -> ".join(str(x) for x in error['loc'])
                        validation_result["validation_errors"].append(
                            f"service_provider.{field_path}: {error['msg']}"
                        )
                    validation_result["is_valid"] = False
            else:
                validation_result["validation_errors"].append(
                    "service_provider must be an object with name and address"
                )
                validation_result["is_valid"] = False


        # Additional validations for other critical fields
        if "amount" in data and data["amount"] is not None:
            try:
                amount = float(data["amount"])
                if amount <= 0:
                    validation_result["validation_warnings"].append(
                        "Amount should be a positive number"
                    )
                validation_result["corrected_data"]["amount"] = amount
            except (ValueError, TypeError):
                validation_result["validation_errors"].append(
                    "Amount must be a valid number"
                )
                validation_result["is_valid"] = False

        # Validate currency format
        if "currency" in data and data["currency"]:
            currency = str(data["currency"]).upper()
            valid_currencies = ["USD", "EUR", "GBP", "HUF", "CHF", "CAD", "AUD", "JPY"]
            if len(currency) != 3 or currency not in valid_currencies:
                validation_result["validation_warnings"].append(
                    f"Currency '{currency}' might not be a standard 3-letter code"
                )
            validation_result["corrected_data"]["currency"] = currency

        # Log validation results
        if validation_result["validation_errors"]:
            logger.warning(f"Data validation failed: {validation_result['validation_errors']}")
        elif validation_result["validation_warnings"]:
            logger.info(f"Data validation warnings: {validation_result['validation_warnings']}")
        else:
            logger.info("Data validation passed successfully")

    except Exception as e:
        logger.error(f"Error during data validation: {e}")
        validation_result["validation_errors"].append(f"Validation error: {str(e)}")
        validation_result["is_valid"] = False

    return validation_result


def format_validation_response(validation_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format validation result for API response

    Args:
        validation_result: Result from validate_extracted_data

    Returns:
        Formatted response with validation metadata
    """
    return {
        "data": validation_result["corrected_data"],
        "validation": {
            "is_valid": validation_result["is_valid"],
            "errors": validation_result["validation_errors"],
            "warnings": validation_result["validation_warnings"],
            "corrections_applied": validation_result["field_corrections"]
        }
    }