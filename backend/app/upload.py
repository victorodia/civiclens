import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, Header, HTTPException, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
# import boto3 (Assume integrated in production)
from .db import get_db
from .ocr_service import extract_votes_from_image
from .models import User
from .security import get_current_user, check_user_status

router = APIRouter(prefix="/upload", tags=["Evidence Storage"])

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

    if not (file.content_type.startswith("image/") or file.content_type.startswith("video/")):
        raise HTTPException(status_code=400, detail="Only image or video evidence is strictly permitted.")

    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    
    # Local Storage for development
    UPLOAD_DIR = os.path.join(os.getcwd(), "app", "static", "uploads")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Perform AI/OCR Analysis if it's an image
    ai_data = {}
    content = await file.read()
    
    if file.content_type.startswith("image/"):
        ai_data = await extract_votes_from_image(content)
        
    # Save file to disk
    with open(file_path, "wb") as buffer:
        buffer.write(content)
    
    # Return local URL for development
    local_url = f"http://127.0.0.1:8001/static/uploads/{unique_filename}"

    return {
        "status": "success",
        "evidence_id": unique_filename,
        "secure_url": local_url,
        "encryption": "LOCAL-DEV",
        "ai_analysis": ai_data
    }
