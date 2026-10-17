import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, Header, HTTPException, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
# import boto3 (Assume integrated in production)
from .db import get_db
from .ocr_service import extract_votes_from_image
from .models import User
from .security import get_current_user, check_user_status, log_audit

router = APIRouter(prefix="/upload", tags=["Evidence Storage"])

# Content is identified by its actual bytes, never the declared Content-Type —
# a declared "image/png" can carry an EXE, and SVG (image/*) carries script.
_MEDIA_MAGIC = (
    (b"\xff\xd8\xff", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def sniff_media_type(content: bytes):
    """Return the file extension for recognized media bytes, else None."""
    if not content:
        return None
    for magic, ext in _MEDIA_MAGIC:
        if content.startswith(magic):
            return ext
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return "mp4"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None

# AWS S3 Storage Config
# AWS_BUCKET_NAME = os.environ.get("AWS_BUCKET_NAME", "civic-lens-secure-forms")
# s3_client = boto3.client('s3')

@router.post("/form-ec8a")
async def secure_image_upload(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    agent: User = Depends(get_current_user),
    x_device_fingerprint: Optional[str] = Header(None),
):
    """
    Receives heavily compressed client-side images.
    Evidence upload is restricted to authenticated, device-bound field agents;
    the result-submission flow rejects any evidence URL it did not issue.
    """

    if agent.role != "agent":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only field agents may upload evidence.")
    if not await check_user_status(str(agent.id), x_device_fingerprint, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Agent account is inactive or device is unauthorized."
        )

    content = await file.read()
    ext = sniff_media_type(content)
    if ext is None:
        raise HTTPException(
            status_code=400,
            detail=("Evidence content is not a recognized media format "
                    "(JPEG, PNG, GIF, WebP, MP4). SVG, executables and other "
                    "file types are not accepted."))

    # The client-supplied filename is never trusted: stored names are a fresh
    # UUID plus the SNIFFED extension, so no path component can survive.
    unique_filename = f"{uuid.uuid4()}.{ext}"

    # Local Storage for development
    UPLOAD_DIR = os.path.join(os.getcwd(), "app", "static", "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Perform AI/OCR Analysis if it's an image
    ai_data = {}
    if ext in ("jpg", "png", "gif", "webp"):
        ai_data = await extract_votes_from_image(content)
        
    # Save file to disk
    with open(file_path, "wb") as buffer:
        buffer.write(content)
    
    # Relative path — works on every deployment domain and does not leak
    # internal hostnames to field devices.
    local_url = f"/static/uploads/{unique_filename}"

    await log_audit(db, actor_id=str(agent.id), actor_role="agent",
                    action="EVIDENCE_UPLOADED",
                    tenant_id=getattr(agent, "client_id", None),
                    target_type="evidence",
                    target_id=unique_filename,
                    details=f"{ext}/{file.content_type} evidence uploaded ({len(content)} bytes)",
                    device_fingerprint=x_device_fingerprint)
    await db.commit()

    return {
        "status": "success",
        "evidence_id": unique_filename,
        "secure_url": local_url,
        "encryption": "LOCAL-DEV",
        "ai_analysis": ai_data
    }
