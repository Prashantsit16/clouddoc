def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_register_success(client, db_session):
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data
    assert "password_hash" not in data

def test_register_duplicate(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 409

def test_login_success(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    response = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_users_me_authenticated(client, db_session):
    client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "password123"}
    )
    login_resp = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "password123"}
    )
    token = login_resp.json()["access_token"]
    
    response = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "password" not in data

def test_users_me_unauthenticated(client):
    response = client.get("/users/me")
    assert response.status_code == 401
