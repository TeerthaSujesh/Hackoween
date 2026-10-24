"""Report File Storage Service.

Handles saving, retrieving, and deleting uploaded lab report files safely on disk.
Files are saved outside the web root using non-predictable UUID storage keys,
storing sha256 checksums for integrity verification and deduplication.
"""

import hashlib
import os
from pathlib import Path
from typing import Tuple
import uuid

from app.core.config import get_settings


class StorageService:
    """Service for managing secure local storage of uploaded lab reports."""

    def __init__(self, base_dir: str | None = None) -> None:
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.storage_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_file(self, file_bytes: bytes, original_filename: str) -> Tuple[str, str, int]:
        """Save raw bytes to disk with a generated unique storage key.

        Args:
            file_bytes: Raw binary content of the file.
            original_filename: Original name of the uploaded file.

        Returns:
            Tuple[str, str, int]: (storage_key, sha256_hash, file_size_bytes)
        """
        # Compute SHA-256 hash
        sha256 = hashlib.sha256(file_bytes).hexdigest()
        file_size = len(file_bytes)

        # Generate unique storage key
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "bin"
        storage_key = f"{uuid.uuid4().hex}.{ext}"

        file_path = self.base_dir / storage_key
        with open(file_path, "wb") as f:
            f.write(file_bytes)

        return storage_key, sha256, file_size

    def get_file_path(self, storage_key: str) -> Path:
        """Resolve and validate the absolute filesystem path for a storage key."""
        target_path = (self.base_dir / storage_key).resolve()
        # Security: Prevent directory traversal
        if not str(target_path).startswith(str(self.base_dir)):
            raise ValueError("Invalid storage key: directory traversal detected.")
        return target_path

    def delete_file(self, storage_key: str) -> bool:
        """Delete a file from disk if it exists."""
        try:
            target_path = self.get_file_path(storage_key)
            if target_path.is_file():
                os.remove(target_path)
                return True
        except Exception:
            pass
        return False


# Singleton instance
storage_service = StorageService()

