from datetime import datetime
from typing import Optional

from pydantic import BaseModel

class DocumentCreate(BaseModel):
    filename: str

class UploadUrlRequest(BaseModel):
    filename: str
    content_type: str

class UploadUrlResponse(BaseModel):
    document_id: int
    upload_url: str

class DocumentResponse(BaseModel):
    id: int
    user_id: int
    filename: str
    object_key: Optional[str] = None
    status: str
    extracted_text: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }
