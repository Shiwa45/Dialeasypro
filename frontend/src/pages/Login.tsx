import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api';
import { useToast } from '../components/ui';

export default function Login() {
  const [workspace, setWorkspace] = useState(localStorage.getItem('tenant_workspace') || '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const { setAuth: storeAuth } = useAuthStore();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspace) {
      showToast('error', 'Workspace required', 'Please enter your workspace ID.');
      return;
    }

    // Save workspace to localStorage so the apiClient interceptor picks it up
    localStorage.setItem('tenant_workspace', workspace);

    setLoading(true);
    try {
      const { data } = await authApi.login(email, password);
      storeAuth(data.agent, data.access, data.refresh, data.must_change_password);
      showToast('success', 'Welcome back!', `Signed in as ${data.agent.name}`);
      navigate('/dashboard');
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Invalid credentials.';
      showToast('error', 'Sign in failed', msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen flex items-center justify-center overflow-hidden"
      style={{ background: '#ffe17c' }}>
      {/* Dot pattern */}
      <div className="dot-pattern" style={{ position: 'absolute', inset: 0, zIndex: 0 }} />

      <div className="relative z-10 w-full px-4" style={{ maxWidth: '440px' }}>
        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="font-heading font-black flex items-center justify-center mb-3"
            style={{ width: '60px', height: '60px', background: '#000', border: '2px solid #000', boxShadow: '6px 6px 0px 0px #171e19', fontSize: '28px', color: '#ffe17c' }}>
            D
          </div>
          <h1 className="font-heading font-black" style={{ fontSize: '2.2rem', color: '#000', lineHeight: 1 }}>DialEasypro</h1>
          <p className="font-medium mt-1" style={{ color: '#171e19', fontSize: '0.85rem' }}>
            Admin CRM — Built for closers.
          </p>
        </div>

        {/* Card */}
        <div style={{ background: '#fff', border: '2px solid #000', boxShadow: '10px 10px 0px 0px #000' }}>
          <div className="px-6 py-4 border-b-2 border-black" style={{ background: '#171e19' }}>
            <h2 className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '1.1rem' }}>Admin Sign In</h2>
            <p style={{ color: '#b7c6c2', fontSize: '0.78rem' }}>Enter your credentials to access the CRM.</p>
          </div>

          <form onSubmit={handleSubmit} className="p-6 flex flex-col gap-4">
            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>WORKSPACE ID</label>
              <div className="flex">
                <input type="text" value={workspace} onChange={(e) => setWorkspace(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))} required
                  className="input-brutal w-full" placeholder="demo"
                  style={{ boxShadow: '3px 3px 0 #000', borderRight: 'none' }} />
              </div>
            </div>
            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>EMAIL ADDRESS</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                className="input-brutal" placeholder="admin@yourcompany.com"
                style={{ boxShadow: '3px 3px 0 #000' }} />
            </div>
            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>PASSWORD</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                className="input-brutal" placeholder="••••••••"
                style={{ boxShadow: '3px 3px 0 #000' }} />
            </div>

            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" style={{ width: '16px', height: '16px', accentColor: '#ffe17c' }} />
                <span className="font-medium" style={{ fontSize: '0.8rem' }}>Remember me</span>
              </label>
              <button type="button" className="font-heading font-bold underline"
                style={{ fontSize: '0.78rem', background: 'none', border: 'none', cursor: 'pointer' }}>
                Forgot password?
              </button>
            </div>

            <button type="submit" disabled={loading}
              className="btn-brutal btn-primary w-full py-3 font-heading font-black"
              style={{ fontSize: '0.95rem', letterSpacing: '0.05em', boxShadow: '6px 6px 0 #000' }}>
              {loading ? '◌ SIGNING IN...' : 'SIGN IN →'}
            </button>
          </form>

          <div className="px-6 py-4 border-t-2 border-black text-center" style={{ background: '#f9f9f9' }}>
            <p className="font-medium" style={{ fontSize: '0.78rem', color: '#555' }}>
              Admin access only. Contact your super admin if you need access.
            </p>
          </div>
        </div>

        <div className="mt-4 p-3 text-center"
          style={{ border: '2px solid #000', background: '#171e19', boxShadow: '4px 4px 0 #000' }}>
          <p className="font-medium" style={{ color: '#b7c6c2', fontSize: '0.75rem' }}>
            <span style={{ color: '#ffe17c', fontWeight: 700 }}>DialEasypro</span> — Powered by www.easyian.com
          </p>
        </div>
      </div>
    </div>
  );
}
