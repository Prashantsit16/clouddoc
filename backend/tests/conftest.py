import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.auth.routes import get_db as auth_get_db
from app.documents.routes import get_db as doc_get_db

# Use in-memory SQLite for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Override dependencies
app.dependency_overrides[auth_get_db] = override_get_db
app.dependency_overrides[doc_get_db] = override_get_db

@pytest.fixture(scope="function")
def db_session():
    """Create a new database session for a test."""
    # Create tables for each test
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop tables after each test
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def test_user_token(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "user1@example.com", "password": "password123"}
    )
    login_resp = client.post(
        "/auth/login",
        json={"email": "user1@example.com", "password": "password123"}
    )
    return login_resp.json()["access_token"]

@pytest.fixture
def test_user2_token(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "user2@example.com", "password": "password123"}
    )
    login_resp = client.post(
        "/auth/login",
        json={"email": "user2@example.com", "password": "password123"}
    )
    return login_resp.json()["access_token"]
