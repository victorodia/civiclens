import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
# import boto3 (Assume integrated in production)
from .ocr_service import extract_votes_from_image

router = APIRouter(prefix="/upload", tags=["Evidence Storage"])

# AWS S3 Storage Config
# AWS_BUCKET_NAME = os.environ.get("AWS_BUCKET_NAME", "civic-lens-secure-forms")
# s3_client = boto3.client('s3')

@router.post("/form-ec8a")
async def secure_image_upload(
    file: UploadFile = File(...),
    # db_session = Depends(get_db)
):
    """
    Receives heavily compressed client-side images.
    Uploads them directly to an S3 bucket configured structurally for 
    SSE-S3 (Server-Side Encryption) so images are encrypted at rest globally.
    """
    
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

