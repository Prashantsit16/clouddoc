from fastapi import Depends, FastAPI
from sqlalchemy import text

from app.database import Base, engine
from app.models import User, Document
from app.auth.routes import router as auth_router
from app.documents.routes import router as document_router
from app.auth.dependencies import get_current_user
from app.models.user import User

app = FastAPI(
    title="CloudDoc API",
    description="Cloud-native document processing platform",
    version="1.0.0"
)
app.include_router(auth_router)
app.include_router(document_router)

# Base.metadata.create_all(bind=engine)

@app.get("/")
def root():
    return {
        "message": "CloudDoc API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }


@app.get("/health/db")
def database_health():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))

        return {
            "database": "connected",
            "result": result.scalar()
        }
@app.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "created_at": current_user.created_at
    }    