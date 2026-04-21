import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import UPLOADS_DIR

CHUNK_SIZE = 8 * 1024 * 1024


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename).strip("._")
    return cleaned or "upload.wav"


async def save_upload_file(upload_file: UploadFile, filename: str) -> Path:
    unique_filename = f"{uuid4().hex}_{filename}"
    destination = UPLOADS_DIR / unique_filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as buffer:
        while True:
            chunk = await upload_file.read(CHUNK_SIZE)
            if not chunk:
                break
            buffer.write(chunk)
    await upload_file.close()
    return destination
