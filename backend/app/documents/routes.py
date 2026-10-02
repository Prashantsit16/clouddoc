import uuid
import re
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import SessionLocal
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    DocumentCreate, 
    DocumentResponse, 
    UploadUrlRequest, 
    UploadUrlResponse
)
from app.storage.s3 import generate_presigned_upload_url

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED
)
def create_document(
    request: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = Document(
        user_id=current_user.id,
        filename=request.filename,
        status="pending"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


ALLOWED_CONTENT_TYPES = {"application/pdf", "text/plain"}

@router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    status_code=status.HTTP_201_CREATED
)
def request_upload_url(
    request: UploadUrlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if request.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported content type"
        )
    
    # Safe filename: keep alphanumerics, dots, dashes, underscores
    safe_filename = re.sub(r'[^a-zA-Z0-9.\-_]', '_', request.filename)
    unique_id = str(uuid.uuid4())
    object_key = f"users/{current_user.id}/documents/{unique_id}-{safe_filename}"
    
    try:
        presigned_url = generate_presigned_upload_url(
            object_key=object_key,
            content_type=request.content_type,
            expiration=600  # 10 minutes
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate upload URL"
        )
        
    document = Document(
        user_id=current_user.id,
        filename=request.filename,
        object_key=object_key,
        status="pending"
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Generated upload URL - Document ID: {document.id}, S3 Object Key: {object_key}, Presigned URL Key matches: True")
    
    return {
        "document_id": document.id,
        "upload_url": presigned_url
    }


@router.get(
    "",
    response_model=List[DocumentResponse]
)
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    documents = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .all()
    )
    return documents


@router.get(
    "/{document_id}",
    response_model=DocumentResponse
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
        
    return document


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )
        
    db.delete(document)
    db.commit()
    return None
