import os
import uuid
from pathlib import Path
from fastapi import UploadFile

# Base directory for uploaded files
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Public URL base (adjust based on your deployment)
PUBLIC_URL_BASE = os.getenv("PUBLIC_URL_BASE", "/uploads")


async def upload_file(file: UploadFile, folder: str) -> str:
    """
    Save an uploaded file and return its public URL.
    
    Args:
        file: The uploaded file
        folder: Subfolder path (e.g., "clients/123/avatar")
    
    Returns:
        Public URL string for the uploaded file
    """
    # Create folder structure
    target_dir = UPLOAD_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename to prevent collisions
    ext = file.filename.split(".")[-1] if file.filename else "bin"
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = target_dir / filename

    # Write file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # Return public URL
    return f"{PUBLIC_URL_BASE}/{folder}/{filename}"


def delete_file(url: str) -> None:
    """Delete a file by its public URL."""
    if not url or not url.startswith(PUBLIC_URL_BASE):
        return
    
    relative_path = url.replace(PUBLIC_URL_BASE, "").lstrip("/")
    file_path = UPLOAD_DIR / relative_path
    
    if file_path.exists():
        file_path.unlink()