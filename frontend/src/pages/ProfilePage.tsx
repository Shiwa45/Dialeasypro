import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { authApi } from '../api';
import { useAuthStore } from '../store/authStore';
import { SectionHeader, Input, Select, useToast } from '../components/ui';

export default function Profile() {
  const { agent, updateAgent } = useAuthStore();
  const { showToast } = useToast();
  const [form, setForm] = useState({
    name: agent?.name ?? '',
    phone: agent?.phone ?? '',
    timezone: agent?.timezone ?? 'Asia/Kolkata',
    language_preference: agent?.language_preference ?? 'en',
  });
  const [pwForm, setPwForm] = useState({ old_password: '', new_password: '', confirm_password: '' });

  const updateMut = useMutation({
    mutationFn: () => authApi.updateMe(form as unknown as import('../types').Agent),
    onSuccess: (res) => { updateAgent(res.data); showToast('success', 'Profile updated', ''); },
    onError: () => showToast('error', 'Update failed', ''),
  });

  const pwMut = useMutation({
    mutationFn: () => authApi.changePassword(pwForm.old_password, pwForm.new_password, pwForm.confirm_password),
    onSuccess: () => { setPwForm({ old_password: '', new_password: '', confirm_password: '' }); showToast('success', 'Password changed', ''); },
    onError: (e: unknown) => showToast('error', 'Failed', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Password change failed.'),
  });

  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(p => ({ ...p, [k]: e.target.value }));
  const pf = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setPwForm(p => ({ ...p, [k]: e.target.value }));

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="My Profile" sub={agent?.email ?? ''} />
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))' }}>
        {/* Profile card */}
        <div className="card p-5">
          <div className="flex items-center gap-3 mb-5 pb-4" style={{ borderBottom: '2px solid #eee' }}>
            <div style={{ width: '56px', height: '56px', background: '#ffe17c', border: '2px solid #000', boxShadow: '3px 3px 0 #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Space Grotesk', fontWeight: 900, fontSize: '1.2rem' }}>
              {agent?.name?.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div className="font-heading font-black" style={{ fontSize: '1rem' }}>{agent?.name}</div>
              <div style={{ fontSize: '0.75rem', color: '#888' }}>{agent?.role_display} · {agent?.email}</div>
              <div><span className="tag mt-1">{agent?.is_tenant_admin ? 'Admin' : agent?.role}</span></div>
            </div>
          </div>
          <div className="font-heading font-black mb-3" style={{ fontSize: '0.88rem' }}>Edit Profile</div>
          <div className="flex flex-col gap-3">
            <Input label="Full Name" value={form.name} onChange={f('name')} />
            <Input label="Phone" value={form.phone} onChange={f('phone')} placeholder="+919876543210" />
            <Select label="Timezone" value={form.timezone} onChange={f('timezone')}>
              <option value="Asia/Kolkata">Asia/Kolkata (IST +5:30)</option>
              <option value="Asia/Dubai">Asia/Dubai (GST +4:00)</option>
              <option value="UTC">UTC</option>
            </Select>
            <Select label="Language" value={form.language_preference} onChange={f('language_preference')}>
              <option value="en">English</option>
              <option value="hi">Hindi</option>
            </Select>
            <button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}
                    className="btn-brutal btn-primary py-2.5 font-heading font-black" style={{ fontSize: '0.88rem', boxShadow: '5px 5px 0 #000' }}>
              {updateMut.isPending ? 'Saving…' : 'Save Profile →'}
            </button>
          </div>
        </div>

        {/* Change password */}
        <div className="card p-5">
          <div className="font-heading font-black mb-4" style={{ fontSize: '0.88rem' }}>Change Password</div>
          <div className="flex flex-col gap-3">
            <Input label="Current Password" type="password" value={pwForm.old_password} onChange={pf('old_password')} />
            <Input label="New Password (min 8 chars)" type="password" value={pwForm.new_password} onChange={pf('new_password')} />
            <Input label="Confirm New Password" type="password" value={pwForm.confirm_password} onChange={pf('confirm_password')} />
            {pwForm.new_password && pwForm.confirm_password && pwForm.new_password !== pwForm.confirm_password && (
              <div style={{ color: '#ef4444', fontSize: '0.78rem' }}>Passwords do not match</div>
            )}
            <button onClick={() => pwMut.mutate()}
                    disabled={pwMut.isPending || !pwForm.old_password || !pwForm.new_password || pwForm.new_password !== pwForm.confirm_password}
                    className="btn-brutal btn-primary py-2.5 font-heading font-black" style={{ fontSize: '0.88rem', boxShadow: '5px 5px 0 #000' }}>
              {pwMut.isPending ? 'Changing…' : 'Change Password →'}
            </button>
          </div>
        </div>

        {/* Account info */}
        <div className="card p-5">
          <div className="font-heading font-black mb-4" style={{ fontSize: '0.88rem' }}>Account Information</div>
          <div className="flex flex-col gap-3">
            {[
              ['Employee ID', agent?.employee_id || '—'],
              ['Total Logins', agent?.total_login_count],
              ['Last Active', agent?.last_active_at ?? '—'],
              ['Account Created', agent?.created_at ?? '—'],
            ].map(([k, v]) => (
              <div key={String(k)} style={{ borderBottom: '1px solid #eee', paddingBottom: '8px' }}>
                <div style={{ fontSize: '0.68rem', color: '#888', fontFamily: 'Space Grotesk', fontWeight: 700, textTransform: 'uppercase' }}>{k}</div>
                <div style={{ fontSize: '0.85rem', marginTop: '2px' }}>{String(v)}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
