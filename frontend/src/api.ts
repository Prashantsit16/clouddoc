const API_URL = '';

function getAuthHeaders() {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  };
}

export async function login(email: string, password: string) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || 'Login failed');
  }
  return response.json();
}

export async function getDocuments() {
  const response = await fetch(`${API_URL}/documents`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error(`Failed to fetch documents: ${response.status}`);
  return response.json();
}

export async function getDocument(id: number) {
  const response = await fetch(`${API_URL}/documents/${id}`, {
    headers: getAuthHeaders()
  });
  if (!response.ok) throw new Error(`Failed to fetch document: ${response.status}`);
  return response.json();
}

export async function requestUploadUrl(filename: string, contentType: string) {
  const response = await fetch(`${API_URL}/documents/upload-url`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ filename, content_type: contentType })
  });
  if (!response.ok) throw new Error(`Failed to get upload URL: ${response.status}`);
  return response.json();
}

export async function uploadToS3(url: string, file: File) {
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': file.type,
    },
    body: file
  });
  if (!response.ok) throw new Error('Failed to upload file to S3');
  return true;
}
