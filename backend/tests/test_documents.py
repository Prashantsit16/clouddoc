import pytest

def test_create_document(client, test_user_token):
    response = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "testdoc.pdf"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["filename"] == "testdoc.pdf"
    assert data["status"] == "pending"
    assert "id" in data

def test_list_own_documents(client, test_user_token, test_user2_token):
    # User 1 creates doc
    client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "doc1.pdf"}
    )
    # User 2 creates doc
    client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user2_token}"},
        json={"filename": "doc2.pdf"}
    )
    
    # List User 1 docs
    response = client.get(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "doc1.pdf"

def test_retrieve_own_document(client, test_user_token):
    create_resp = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "testdoc.pdf"}
    )
    doc_id = create_resp.json()["id"]
    
    response = client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "testdoc.pdf"

def test_prevent_access_other_user_document(client, test_user_token, test_user2_token):
    create_resp = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "testdoc.pdf"}
    )
    doc_id = create_resp.json()["id"]
    
    response = client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user2_token}"}
    )
    assert response.status_code == 404

def test_delete_own_document(client, test_user_token):
    create_resp = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "testdoc.pdf"}
    )
    doc_id = create_resp.json()["id"]
    
    del_resp = client.delete(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert del_resp.status_code == 204
    
    get_resp = client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_resp.status_code == 404

def test_prevent_deletion_other_user_document(client, test_user_token, test_user2_token):
    create_resp = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "testdoc.pdf"}
    )
    doc_id = create_resp.json()["id"]
    
    del_resp = client.delete(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user2_token}"}
    )
    assert del_resp.status_code == 404
    
    # Verify it still exists for user 1
    get_resp = client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_resp.status_code == 200

def test_invalid_document_data(client, test_user_token):
    response = client.post(
        "/documents",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={} # Missing filename
    )
    assert response.status_code == 422
