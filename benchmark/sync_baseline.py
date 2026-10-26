import os
import sys
import time
import fitz  # PyMuPDF
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Ensure backend modules can be imported
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Base, engine
from app.models.document import Document
from app.models.user import User
from app.auth.dependencies import get_current_user

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Exact extraction logic used in worker/main.py"""
    text = ""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()
    except Exception as e:
        raise ValueError("Invalid or corrupted PDF file") from e

def process_document_synchronous(
    file_bytes: bytes,
    filename: str,
    user_id: int,
    db: Session
) -> Document:
    """
    Executes the exact database insertion and PyMuPDF text extraction
    synchronously in the request cycle, matching production validation and schema.
    """
    if not (filename.lower().endswith(".pdf") or filename.lower().endswith(".txt")):
        raise ValueError("Unsupported content type")

    # In synchronous mode, extraction runs directly before completion
    extracted_text = extract_text_from_pdf(file_bytes)
    
    document = Document(
        user_id=user_id,
        filename=filename,
        object_key=f"sync-upload/{user_id}/{filename}",
        status="completed",
        extracted_text=extracted_text,
        error_message=None
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document

from fastapi import FastAPI, Depends, HTTPException, Request, Header, status

# Standalone FastAPI route for synchronous comparison
sync_app = FastAPI(title="CloudDoc Synchronous Baseline Endpoint")

@sync_app.post("/documents/sync-upload", status_code=status.HTTP_201_CREATED)
async def sync_upload_document(
    request: Request,
    x_filename: str = Header(default="upload.pdf"),
    db: Session = Depends(SessionLocal),
    current_user: User = Depends(get_current_user)
):
    start_time = time.perf_counter()
    file_bytes = await request.body()
    
    try:
        doc = process_document_synchronous(
            file_bytes=file_bytes,
            filename=file.filename or "upload.pdf",
            user_id=current_user.id,
            db=db
        )
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "processing_time_ms": elapsed_ms
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    finally:
        db.close()
