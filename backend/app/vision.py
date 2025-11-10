"""
Vision model integration using vLLM or OpenRouter with OpenAI-compatible API
"""
import json
import base64
import logging
from typing import Dict, Any, Optional
from openai import OpenAI
from PIL import Image

from .config import config
from .utils import image_to_base64, prepare_image_for_vision

logger = logging.getLogger(__name__)


class VisionModel:
    """Wrapper for vision model with OpenAI-compatible API (vLLM or OpenRouter)"""

    def __init__(self):
        self.provider = config.provider

        if self.provider == "openrouter":
            # OpenRouter configuration
            if not config.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable is required when using OpenRouter provider")

            self.client = OpenAI(
                api_key=config.openrouter_api_key,
                base_url=config.openrouter_api_base
            )
            self.model_name = config.openrouter_model
            logger.info(f"Initialized OpenRouter provider with model: {self.model_name}")
        else:
            # vLLM configuration (default)
            self.client = OpenAI(
                api_key="EMPTY",  # vLLM doesn't require API key
                base_url=config.vllm_api_base
            )
            self.model_name = config.model_name
            logger.info(f"Initialized vLLM provider with model: {self.model_name}")

    def analyze_image(
        self,
        image: Image.Image,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> Dict[str, Any]:
        """
        Analyze an image using the vision model

        Args:
            image: PIL Image object
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            temperature: Sampling temperature (lower = more deterministic)
            max_tokens: Maximum tokens to generate

        Returns:
            Dictionary with 'success', 'data', 'error', and 'raw_response' keys
        """
        try:
            # Prepare image for vision model
            processed_image = prepare_image_for_vision(image)

            # Convert image to base64
            image_base64 = image_to_base64(processed_image, format="PNG")
            image_url = f"data:image/png;base64,{image_base64}"

            # Construct messages for the API
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        },
                        {
                            "type": "text",
                            "text": user_prompt
                        }
                    ]
                }
            ]

            # Call the vision API
            api_base = config.openrouter_api_base if self.provider == "openrouter" else config.vllm_api_base
            logger.info(f"Calling {self.provider} API with model {self.model_name}")
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )

            # Extract the response text
            raw_response = response.choices[0].message.content
            logger.info(f"Received response from {self.provider}: {raw_response[:200]}...")

            # Extract token usage information
            token_usage = None
            if hasattr(response, 'usage') and response.usage:
                token_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                logger.info(f"Token usage: {token_usage}")

            # Try to parse as JSON
            try:
                # Clean the response - remove markdown code blocks if present
                cleaned_response = raw_response.strip()
                if cleaned_response.startswith("```json"):
                    cleaned_response = cleaned_response[7:]
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response[3:]
                if cleaned_response.endswith("```"):
                    cleaned_response = cleaned_response[:-3]
                cleaned_response = cleaned_response.strip()

                data = json.loads(cleaned_response)

                return {
                    "success": True,
                    "data": data,
                    "error": None,
                    "raw_response": raw_response,
                    "token_usage": token_usage
                }
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON response: {e}")
                return {
                    "success": False,
                    "data": None,
                    "error": f"Failed to parse JSON: {str(e)}",
                    "raw_response": raw_response,
                    "token_usage": token_usage
                }

        except Exception as e:
            logger.error(f"Error analyzing image: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error": str(e),
                "raw_response": None,
                "token_usage": None
            }

    def analyze_images(
        self,
        images: list[Image.Image],
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_tokens: int = 2000
    ) -> list[Dict[str, Any]]:
        """
        Analyze multiple images (e.g., pages from a PDF)

        Args:
            images: List of PIL Image objects
            system_prompt: System prompt for the model
            user_prompt: User prompt for the model
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            List of result dictionaries, one per image
        """
        results = []
        for i, image in enumerate(images):
            logger.info(f"Analyzing image {i+1}/{len(images)}")
            result = self.analyze_image(
                image=image,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            results.append(result)

        return results


# Global vision model instance
vision_model = VisionModel()
