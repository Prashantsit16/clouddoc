import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDocuments, requestUploadUrl, uploadToS3, getDocument } from '../api';
import { FileText, Upload, LogOut, RefreshCw, X, CheckCircle, AlertCircle, Clock } from 'lucide-react';

export default function Dashboard() {
  const navigate = useNavigate();
  const [documents, setDocuments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Upload State
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState('');
  const [error, setError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Result Viewer State
  const [selectedDoc, setSelectedDoc] = useState<any>(null);

  const documentsRef = useRef<any[]>([]);

  const fetchDocuments = async () => {
    try {
      const docs = await getDocuments();
      const sorted = docs.sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
      setDocuments(sorted);
      documentsRef.current = sorted;
    } catch (err) {
      if (err instanceof Error && err.message.includes('401')) {
        handleLogout();
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!localStorage.getItem('token')) {
      navigate('/login');
      return;
    }
    fetchDocuments();
    
    // Poll for updates every 5 seconds if there are pending/processing docs
    const interval = setInterval(() => {
      const needsUpdate = documentsRef.current.some(d => d.status === 'pending' || d.status === 'processing');
      if (needsUpdate) {
        fetchDocuments();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [navigate]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    navigate('/login');
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/pdf') {
      setError('Please select a valid PDF file.');
      return;
    }

    setError('');
    setIsUploading(true);
    setUploadStatus('Requesting secure upload link...');

    try {
      // 1. Get Presigned URL
      const { upload_url } = await requestUploadUrl(file.name, file.type);
      
      setUploadStatus('Uploading securely to S3...');
      // 2. Upload to S3 directly
      await uploadToS3(upload_url, file);
      
      setUploadStatus('Upload complete! Document is queuing for processing.');
      
      // Clear input & refresh list
      if (fileInputRef.current) fileInputRef.current.value = '';
      fetchDocuments();
      
      setTimeout(() => {
        setIsUploading(false);
        setUploadStatus('');
      }, 3000);
      
    } catch (err: any) {
      setError(err.message || 'An error occurred during upload.');
      setIsUploading(false);
      setTimeout(() => setError(''), 5000);
    }
  };

  const handleViewResult = async (docId: number) => {
    try {
      const doc = await getDocument(docId);
      setSelectedDoc(doc);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="app-container animate-fade-in">
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <FileText size={32} color="var(--primary)" />
          <h1 style={{ margin: 0 }}>CloudDoc Dashboard</h1>
        </div>
        <button className="btn btn-secondary" onClick={handleLogout}>
          <LogOut size={18} /> Logout
        </button>
      </header>

      <div className="glass-card" style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 style={{ margin: 0 }}>Your Documents</h2>
          
          <div>
            <input 
              type="file" 
              accept="application/pdf" 
              ref={fileInputRef} 
              style={{ display: 'none' }} 
              onChange={handleFileSelect}
              disabled={isUploading}
            />
            <button 
              className="btn" 
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
            >
              {isUploading ? <RefreshCw size={18} className="spin" /> : <Upload size={18} />}
              {isUploading ? 'Uploading...' : 'Upload PDF'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.2)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '1rem' }}>
            <AlertCircle size={18} style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} />
            {error}
          </div>
        )}

        {isUploading && uploadStatus && (
          <div style={{ padding: '1rem', background: 'rgba(59, 130, 246, 0.2)', color: 'var(--primary)', borderRadius: '8px', marginBottom: '1rem' }}>
            <RefreshCw size={18} className="spin" style={{ verticalAlign: 'middle', marginRight: '0.5rem' }} />
            {uploadStatus}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>Loading documents...</div>
        ) : documents.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
            <FileText size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>No documents found. Upload your first PDF to get started.</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {documents.map(doc => (
                  <tr key={doc.id}>
                    <td style={{ fontWeight: 500 }}>{doc.filename}</td>
                    <td className="text-muted">{new Date(doc.created_at).toLocaleString()}</td>
                    <td>
                      <span className={`badge ${doc.status}`}>
                        {doc.status === 'completed' && <CheckCircle size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }}/>}
                        {doc.status === 'failed' && <AlertCircle size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }}/>}
                        {(doc.status === 'pending' || doc.status === 'processing') && <Clock size={14} style={{ verticalAlign: 'middle', marginRight: '4px' }}/>}
                        {doc.status}
                      </span>
                    </td>
                    <td>
                      {doc.status === 'completed' && (
                        <button className="btn btn-secondary" style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }} onClick={() => handleViewResult(doc.id)}>
                          View Result
                        </button>
                      )}
                      {doc.status === 'failed' && (
                        <span className="text-muted" style={{ fontSize: '0.875rem' }} title={doc.error_message}>View Error</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Result Viewer Modal */}
      {selectedDoc && (
        <div className="modal-overlay" onClick={() => setSelectedDoc(null)}>
          <div className="glass-card modal-content animate-fade-in" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <h3 style={{ margin: 0 }}>{selectedDoc.filename} - Extracted Text</h3>
              <button className="btn-secondary" style={{ border: 'none', padding: '0.5rem', cursor: 'pointer' }} onClick={() => setSelectedDoc(null)}>
                <X size={24} />
              </button>
            </div>
            <div style={{ 
              background: 'rgba(0,0,0,0.3)', 
              padding: '1.5rem', 
              borderRadius: '8px', 
              maxHeight: '60vh', 
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: 'monospace',
              fontSize: '0.9rem',
              lineHeight: '1.5'
            }}>
              {selectedDoc.extracted_text || 'No text extracted.'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
