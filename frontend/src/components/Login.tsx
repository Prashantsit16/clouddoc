import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api';
import { Cloud, Lock, Mail, ArrowRight } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    try {
      const data = await login(email, password);
      localStorage.setItem('token', data.access_token);
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Failed to login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
      <div className="glass-card animate-fade-in" style={{ maxWidth: '400px', width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <Cloud size={48} color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
          <h2>Welcome to CloudDoc</h2>
          <p className="text-muted">Sign in to manage your documents</p>
        </div>

        {error && (
          <div style={{ padding: '0.75rem', background: 'rgba(239, 68, 68, 0.2)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.875rem' }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div style={{ position: 'relative' }}>
            <Mail size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="email" 
              className="input" 
              placeholder="Email address" 
              style={{ paddingLeft: '2.5rem' }}
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>
          
          <div style={{ position: 'relative' }}>
            <Lock size={18} style={{ position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="password" 
              className="input" 
              placeholder="Password" 
              style={{ paddingLeft: '2.5rem' }}
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>

          <button type="submit" className="btn" style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem' }} disabled={loading}>
            {loading ? 'Signing in...' : (
              <>Sign In <ArrowRight size={18} /></>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
