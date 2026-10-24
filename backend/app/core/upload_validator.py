"""Upload File Validation.

Validates uploaded files by size, MIME type, and magic bytes to prevent
arbitrary file upload vulnerabilities and invalid file formats.
"""

from typing import Tuple
from fastapi import HTTPException, status

# Allowed MIME types and their corresponding magic byte prefixes
ALLOWED_MAGIC_BYTES = {
    b"%PDF-": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_file_upload(file_bytes: bytes, original_filename: str) -> Tuple[str, str]:
    """Validate uploaded file size, extension, and magic bytes.

    Args:
        file_bytes: Raw bytes of the uploaded file.
        original_filename: Original name of the uploaded file.

    Returns:
        Tuple[str, str]: (sanitized_filename, verified_mime_type)

    Raises:
        HTTPException: If the file is empty, exceeds size limit, has unsupported
                       extension, or fails magic bytes inspection.
    """
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    file_size = len(file_bytes)
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size ({file_size / (1024 * 1024):.1f} MB) exceeds maximum limit of 10 MB.",
        )

    # Sanitize and extract extension
    clean_filename = original_filename.strip().replace("\\", "/").split("/")[-1]
    if not clean_filename or "." not in clean_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: missing extension.",
        )

    ext = clean_filename.rsplit(".", 1)[-1].lower()
    allowed_extensions = {"pdf", "jpg", "jpeg", "png"}
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '.{ext}'. Supported formats are: PDF, JPEG, PNG.",
        )

    # Validate file magic bytes
    verified_mime: str | None = None
    for magic, mime in ALLOWED_MAGIC_BYTES.items():
        if file_bytes.startswith(magic):
            verified_mime = mime
            break

    if not verified_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match supported PDF or Image headers.",
        )

    return clean_filename, verified_mime

