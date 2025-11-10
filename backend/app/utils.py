"""
Utility functions for file processing
"""
import base64
import io
from pathlib import Path
from typing import List, Union
from PIL import Image
import pdf2image


def pdf_to_images(pdf_path: Union[str, Path]) -> List[Image.Image]:
    """
    Convert PDF to list of PIL Images

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of PIL Image objects, one per page
    """
    images = pdf2image.convert_from_path(pdf_path, dpi=200)
    return images


def pdf_bytes_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    """
    Convert PDF bytes to list of PIL Images

    Args:
        pdf_bytes: PDF file as bytes

    Returns:
        List of PIL Image objects, one per page
    """
    images = pdf2image.convert_from_bytes(pdf_bytes, dpi=200)
    return images


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """
    Convert PIL Image to base64 string

    Args:
        image: PIL Image object
        format: Image format (PNG, JPEG, etc.)

    Returns:
        Base64 encoded string
    """
    buffered = io.BytesIO()
    image.save(buffered, format=format)
    img_bytes = buffered.getvalue()
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    return img_base64


def bytes_to_image(image_bytes: bytes) -> Image.Image:
    """
    Convert bytes to PIL Image

    Args:
        image_bytes: Image file as bytes

    Returns:
        PIL Image object
    """
    return Image.open(io.BytesIO(image_bytes))


def prepare_image_for_vision(image: Image.Image, max_size: tuple = (1024, 1024)) -> Image.Image:
    """
    Prepare image for vision model by resizing if needed

    Args:
        image: PIL Image object
        max_size: Maximum width and height

    Returns:
        Processed PIL Image object
    """
    # Convert to RGB if necessary
    if image.mode not in ('RGB', 'L'):
        image = image.convert('RGB')

    # Resize if image is too large
    if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)

    return image


def validate_file_extension(filename: str, allowed_extensions: set) -> bool:
    """
    Validate file extension

    Args:
        filename: Name of the file
        allowed_extensions: Set of allowed extensions (e.g., {'.pdf', '.jpg'})

    Returns:
        True if extension is allowed
    """
    ext = Path(filename).suffix.lower()
    return ext in allowed_extensions
