import pytest

def test_request_upload_url_unauthenticated(client):
    response = client.post(
        "/documents/upload-url",
        json={"filename": "test.pdf", "content_type": "application/pdf"}
    )
    assert response.status_code == 401

def test_request_upload_url_invalid_content_type(client, test_user_token):
    response = client.post(
        "/documents/upload-url",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "script.js", "content_type": "application/javascript"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported content type"

def test_request_upload_url_success(client, test_user_token, mocker):
    # Mock the presigned URL generation
    mock_generate = mocker.patch("app.documents.routes.generate_presigned_upload_url")
    mock_generate.return_value = "https://s3.amazonaws.com/fake-bucket/fake-url"

    response = client.post(
        "/documents/upload-url",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "My Report.pdf", "content_type": "application/pdf"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "document_id" in data
    assert data["upload_url"] == "https://s3.amazonaws.com/fake-bucket/fake-url"
    
    # Verify mock was called correctly
    mock_generate.assert_called_once()
    call_args = mock_generate.call_args[1]
    assert call_args["content_type"] == "application/pdf"
    assert "My_Report.pdf" in call_args["object_key"]
    
    # Verify document was actually created in the DB
    doc_id = data["document_id"]
    get_resp = client.get(
        f"/documents/{doc_id}",
        headers={"Authorization": f"Bearer {test_user_token}"}
    )
    assert get_resp.status_code == 200
    doc_data = get_resp.json()
    assert doc_data["filename"] == "My Report.pdf"
    assert doc_data["status"] == "pending"
    assert doc_data["object_key"] == call_args["object_key"]
    # Check that object_key starts with users/{user_id}/
    assert doc_data["object_key"].startswith(f"users/{doc_data['user_id']}/documents/")

def test_request_upload_url_s3_failure(client, test_user_token, mocker):
    # Mock an exception during S3 URL generation
    mock_generate = mocker.patch("app.documents.routes.generate_presigned_upload_url")
    mock_generate.side_effect = Exception("AWS Error")

    response = client.post(
        "/documents/upload-url",
        headers={"Authorization": f"Bearer {test_user_token}"},
        json={"filename": "test.pdf", "content_type": "application/pdf"}
    )
    
    assert response.status_code == 500
    assert response.json()["detail"] == "Could not generate upload URL"
