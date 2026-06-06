import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api';
import {
  SectionHeader, Modal, Input, Select, ConfirmDialog,
  Pagination, Spinner, EmptyState, useToast, StatusBadge,
} from '../components/ui';
import { fmtRelative } from '../utils/fmt';

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'manager', label: 'Manager' },
  { value: 'senior_agent', label: 'Senior Agent' },
  { value: 'agent', label: 'Agent' },
  { value: 'trainee', label: 'Trainee' },
];

export default function Agents() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [page, setPage] = useState(1);
  const [showModal, setShowModal] = useState(false);
  const [editAgent, setEditAgent] = useState<Record<string, unknown>>({});
  const [confirmDeactivate, setConfirmDeactivate] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const [pwdAgent, setPwdAgent] = useState<{ id: number; name: string } | null>(null);
  const [pwdForm, setPwdForm] = useState({ new_password: '', confirm_password: '', require_change_on_login: false });

  const { data, isLoading } = useQuery({
    queryKey: ['agents', page, search],
    queryFn: () => authApi.listAgents({ page, page_size: 20, ...(search ? { search } : {}) }).then(r => r.data),
    placeholderData: prev => prev,
  });

  const saveMut = useMutation({
    mutationFn: () =>
      editAgent.id
        ? authApi.updateAgent(Number(editAgent.id), editAgent as unknown as import('../types').Agent)
        : authApi.createAgent(editAgent),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] });
      setShowModal(false);
      setEditAgent({});
      showToast('success', 'Agent saved', '');
    },
    onError: (e: unknown) =>
      showToast('error', 'Error', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Failed'),
  });

  const deactivateMut = useMutation({
    mutationFn: (id: number) => authApi.updateAgent(id, { is_active: false } as unknown as import('../types').Agent),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['agents'] });
      setConfirmDeactivate(null);
      showToast('info', 'Agent deactivated', '');
    },
  });

  const closePwdModal = () => {
    setPwdAgent(null);
    setPwdForm({ new_password: '', confirm_password: '', require_change_on_login: false });
  };

  const setPasswordMut = useMutation({
    mutationFn: () =>
      authApi.setAgentPassword(
        pwdAgent!.id,
        pwdForm.new_password,
        pwdForm.confirm_password,
        pwdForm.require_change_on_login,
      ),
    onSuccess: () => {
      showToast('success', 'Password updated', `New password set for ${pwdAgent?.name}.`);
      closePwdModal();
    },
    onError: (e: unknown) =>
      showToast('error', 'Error', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Failed to set password'),
  });

  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setEditAgent(p => ({ ...p, [k]: e.target.value }));

  const agents = data?.results ?? [];

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Agents" sub={`${data?.count ?? 0} agents`}>
        <button
          onClick={() => { setEditAgent({}); setShowModal(true); }}
          className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
          style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}
        >
          + New Agent
        </button>
      </SectionHeader>

      {/* Search */}
      <div className="card card-sm p-3 flex gap-2">
        <input
          placeholder="Search agents by name or email…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          className="input-brutal flex-1"
          style={{ boxShadow: '2px 2px 0 #000' }}
        />
      </div>

      {isLoading ? (
        <Spinner />
      ) : agents.length === 0 ? (
        <EmptyState
          icon="◉"
          title="No agents found"
          action={{ label: '+ Add Agent', onClick: () => setShowModal(true) }}
        />
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="table-brutal">
            <thead>
              <tr>
                {['Agent', 'Role', 'Phone', 'Status', 'Online', 'Logins', 'Last Active', 'Actions'].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {agents.map(agent => (
                <tr key={agent.id}>
                  <td>
                    <div className="flex items-center gap-2">
                      <div
                        style={{
                          width: '34px', height: '34px', background: '#b7c6c2',
                          border: '2px solid #000', display: 'flex', alignItems: 'center',
                          justifyContent: 'center', fontSize: '0.72rem',
                          fontFamily: 'Space Grotesk', fontWeight: 900, flexShrink: 0,
                        }}
                      >
                        {agent.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <div className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{agent.name}</div>
                        <div style={{ fontSize: '0.7rem', color: '#888' }}>{agent.email}</div>
                      </div>
                    </div>
                  </td>
                  <td><span className="tag">{agent.role_display}</span></td>
                  <td className="font-mono" style={{ fontSize: '0.78rem' }}>{agent.phone || '—'}</td>
                  <td><StatusBadge status={agent.is_active ? 'active' : 'inactive'} /></td>
                  <td>
                    <span style={{
                      width: '10px', height: '10px', borderRadius: '50%',
                      background: agent.is_online ? '#22c55e' : '#d1d5db',
                      display: 'inline-block', border: '2px solid #000',
                    }} />
                  </td>
                  <td style={{ fontSize: '0.82rem' }}>{agent.total_login_count}</td>
                  <td style={{ fontSize: '0.75rem', color: '#888' }}>{fmtRelative(agent.last_active_at)}</td>
                  <td>
                    <div className="flex gap-1">
                      <button
                        onClick={() => { setEditAgent(agent as unknown as Record<string, unknown>); setShowModal(true); }}
                        className="btn-brutal btn-yellow px-2 py-1 font-heading font-bold"
                        style={{ fontSize: '0.68rem' }}
                      >
                        Edit
                      </button>
                      {!agent.is_tenant_admin && (
                        <button
                          onClick={() => setPwdAgent({ id: agent.id, name: agent.name })}
                          className="btn-brutal btn-secondary px-2 py-1 font-heading font-bold"
                          style={{ fontSize: '0.68rem' }}
                        >
                          Password
                        </button>
                      )}
                      {agent.is_active && !agent.is_tenant_admin && (
                        <button
                          onClick={() => setConfirmDeactivate(agent.id)}
                          className="btn-brutal btn-danger px-2 py-1 font-heading font-bold"
                          style={{ fontSize: '0.68rem' }}
                        >
                          Deactivate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="px-4 pb-4">
            <Pagination page={page} totalPages={data?.total_pages ?? 1} onPageChange={setPage} />
          </div>
        </div>
      )}

      {/* Agent Form Modal */}
      {showModal && (
        <Modal
          title={editAgent.id ? `Edit: ${editAgent.name}` : 'New Agent'}
          onClose={() => { setShowModal(false); setEditAgent({}); }}
          maxWidth="580px"
        >
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Input label="Full Name *" value={String(editAgent.name ?? '')} onChange={f('name')} placeholder="Rahul Sharma" />
            </div>
            <Input label="Email *" type="email" value={String(editAgent.email ?? '')} onChange={f('email')} />
            <Input label="Phone" value={String(editAgent.phone ?? '')} onChange={f('phone')} placeholder="+919876543210" />
            <Input label="Employee ID" value={String(editAgent.employee_id ?? '')} onChange={f('employee_id')} />
            <Select label="Role *" value={String(editAgent.role ?? 'agent')} onChange={f('role')}>
              {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
            {!editAgent.id && (
              <>
                <Input label="Password *" type="password" value={String(editAgent.password ?? '')} onChange={f('password')} />
                <Input label="Confirm Password *" type="password" value={String(editAgent.confirm_password ?? '')} onChange={f('confirm_password')} />
              </>
            )}
          </div>
          {saveMut.isError && (
            <div style={{ background: '#fee2e2', border: '2px solid #ef4444', padding: '8px 12px', fontSize: '0.8rem', marginTop: '12px' }}>
              {(saveMut.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'An error occurred.'}
            </div>
          )}
          <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
            <button onClick={() => { setShowModal(false); setEditAgent({}); }} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button
              onClick={() => saveMut.mutate()}
              disabled={saveMut.isPending}
              className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black"
              style={{ boxShadow: '5px 5px 0 #000' }}
            >
              {saveMut.isPending ? '◌ Saving…' : editAgent.id ? 'Save Changes →' : 'Create Agent →'}
            </button>
          </div>
        </Modal>
      )}

      {confirmDeactivate !== null && (
        <ConfirmDialog
          title="Deactivate Agent?"
          message="The agent will lose all access to the CRM immediately."
          confirmLabel="Deactivate"
          danger
          onConfirm={() => deactivateMut.mutate(confirmDeactivate)}
          onCancel={() => setConfirmDeactivate(null)}
        />
      )}

      {/* Set Password Modal */}
      {pwdAgent && (
        <Modal
          title={`Set Password: ${pwdAgent.name}`}
          onClose={closePwdModal}
          maxWidth="440px"
        >
          <div className="flex flex-col gap-3">
            <Input
              label="New Password *"
              type="password"
              value={pwdForm.new_password}
              onChange={e => setPwdForm(p => ({ ...p, new_password: e.target.value }))}
              placeholder="At least 8 characters"
            />
            <Input
              label="Confirm Password *"
              type="password"
              value={pwdForm.confirm_password}
              onChange={e => setPwdForm(p => ({ ...p, confirm_password: e.target.value }))}
            />
            <label className="flex items-center gap-2 cursor-pointer" style={{ fontSize: '0.8rem' }}>
              <input
                type="checkbox"
                checked={pwdForm.require_change_on_login}
                onChange={e => setPwdForm(p => ({ ...p, require_change_on_login: e.target.checked }))}
                style={{ width: '16px', height: '16px', accentColor: '#ffe17c' }}
              />
              <span className="font-medium">Require agent to change password on next login</span>
            </label>
            {pwdForm.new_password.length > 0 && pwdForm.new_password.length < 8 && (
              <div style={{ fontSize: '0.72rem', color: '#ef4444' }}>Password must be at least 8 characters.</div>
            )}
            {pwdForm.confirm_password.length > 0 && pwdForm.new_password !== pwdForm.confirm_password && (
              <div style={{ fontSize: '0.72rem', color: '#ef4444' }}>Passwords do not match.</div>
            )}
          </div>
          <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
            <button onClick={closePwdModal} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button
              onClick={() => setPasswordMut.mutate()}
              disabled={
                setPasswordMut.isPending ||
                pwdForm.new_password.length < 8 ||
                pwdForm.new_password !== pwdForm.confirm_password
              }
              className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black"
              style={{ boxShadow: '5px 5px 0 #000' }}
            >
              {setPasswordMut.isPending ? '◌ Setting…' : 'Set Password →'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
