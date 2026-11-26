import hashlib
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException

from .config import STORAGE_DIR

CROP_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.png")  # a plain file name: no separators, no leading dot


def upload_path(job_id: uuid.UUID) -> Path:
    return STORAGE_DIR / "uploads" / f"{job_id}.pdf"


def exam_dir(exam_id: uuid.UUID) -> Path:
    """holds blank/crops/*.png and, for exams with solution ink, ink/crops/*.png"""
    return STORAGE_DIR / "exams" / str(exam_id)


def doc_dir(document_id: uuid.UUID) -> Path:
    """holds file.pdf, the original study PDF that the viewer shows"""
    return STORAGE_DIR / "documents" / str(document_id)


def save_capped(file: BinaryIO, path: Path, limit: int) -> str:
    """Copies `file` to `path` and returns its sha256; past `limit` bytes nothing is kept and the answer is 413."""
    digest, size = hashlib.sha256(), 0
    with open(path, "wb") as f:
        while block := file.read(1 << 20):
            size += len(block)
            if size > limit:
                f.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, detail={"code": "too_large"})
            digest.update(block)
            f.write(block)
    return digest.hexdigest()
