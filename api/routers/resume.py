"""
Resume endpoints — upload PDF, retrieve parsed profile.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger

from api.dependencies import verify_api_key
from config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])

_PROFILE_PATH = settings.DATA_DIR / "candidate_profile.json"
_MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", status_code=201)
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload a PDF resume. Parses it with GPT-4o-mini and stores the
    candidate profile to data/candidate_profile.json.
    """
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=415,
            detail="Only PDF files are accepted (content-type: application/pdf)",
        )

    content = await file.read()
    if len(content) > _MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds 10 MB limit")

    # Write to a temp file so the parser can open it by path
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from parsers.resume_parser import parse_resume
        profile = parse_resume(tmp_path, save=True)
        logger.info(f"Resume uploaded and parsed for: {profile.get('name', 'unknown')}")
    except Exception as exc:
        logger.exception("Resume parsing failed")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"message": "Resume parsed successfully", "profile": profile}


@router.get("/profile")
def get_profile():
    """Return the currently stored candidate profile."""
    if not _PROFILE_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No resume profile found — upload a PDF first via POST /resume/upload",
        )
    return json.loads(_PROFILE_PATH.read_text())
