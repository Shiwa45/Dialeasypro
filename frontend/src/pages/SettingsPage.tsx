import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsApi, callsApi, authApi } from '../api';
import { SectionHeader, Modal, Input, Select, Spinner, useToast, EmptyState } from '../components/ui';

export default function Settings() {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<'custom-fields' | 'dispositions' | 'teams' | 'billing'>('custom-fields');
  const [showFieldModal, setShowFieldModal] = useState(false);
  const [fieldForm, setFieldForm] = useState({ name: '', field_type: 'text', is_required: false, placeholder: '' });

  const cfQ = useQuery({ queryKey: ['custom-fields'], queryFn: () => leadsApi.listCustomFields().then(r => r.data), enabled: tab === 'custom-fields' });
  const dispQ = useQuery({ queryKey: ['dispositions'], queryFn: () => callsApi.dispositions().then(r => r.data), enabled: tab === 'dispositions' });
  const teamsQ = useQuery({ queryKey: ['teams'], queryFn: () => authApi.listTeams().then(r => r.data), enabled: tab === 'teams' });

  const createFieldMut = useMutation({
    mutationFn: () => leadsApi.createCustomField(fieldForm as unknown as import('../types').CustomField),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['custom-fields'] });
      setShowFieldModal(false);
      setFieldForm({ name: '', field_type: 'text', is_required: false, placeholder: '' });
      showToast('success', 'Custom field created', '');
    },
    onError: (e: unknown) => showToast('error', 'Error', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Failed — you may have reached your plan limit.'),
  });

  const FIELD_TYPES = ['text', 'textarea', 'number', 'date', 'dropdown', 'checkbox', 'phone', 'url'];
  const TABS = [
    { k: 'custom-fields', l: '☰ Custom Fields' },
    { k: 'dispositions', l: '☎ Call Dispositions' },
    { k: 'teams', l: '◉ Teams' },
    { k: 'billing', l: '₹ Billing' },
  ] as const;

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Settings" sub="Configure your CRM workspace" />

      <div style={{ display: 'flex', borderBottom: '2px solid #000', overflowX: 'auto' }}>
        {TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} className="font-heading font-bold px-4 py-2.5"
                  style={{ background: tab === t.k ? '#ffe17c' : '#fff', border: 'none', borderRight: '2px solid #000', cursor: 'pointer', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
            {t.l}
          </button>
        ))}
      </div>

      {/* Custom Fields */}
      {tab === 'custom-fields' && (
        <div>
          <div className="flex justify-end mb-3">
            <button onClick={() => setShowFieldModal(true)}
                    className="btn-brutal btn-primary px-4 py-2 font-heading font-black" style={{ fontSize: '0.82rem', boxShadow: '4px 4px 0 #000' }}>
              + Add Custom Field
            </button>
          </div>
          {cfQ.isLoading ? <Spinner /> : (cfQ.data ?? []).length === 0 ? (
            <EmptyState icon="☰" title="No custom fields"
                        message="Add custom fields to capture extra lead data specific to your industry (e.g., Property Type, Budget Range, Project Name)."
                        action={{ label: '+ Add Custom Field', onClick: () => setShowFieldModal(true) }} />
          ) : (
            <div className="card" style={{ overflowX: 'auto' }}>
              <table className="table-brutal">
                <thead><tr>{['Field Name', 'Key', 'Type', 'Required', 'Placeholder', 'Active'].map(h => <th key={h}>{h}</th>)}</tr></thead>
                <tbody>
                  {(cfQ.data ?? []).map(f => (
                    <tr key={f.id}>
                      <td className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{f.name}</td>
                      <td className="font-mono" style={{ fontSize: '0.75rem', color: '#555' }}>{f.field_key}</td>
                      <td><span className="tag">{f.field_type}</span></td>
                      <td>{f.is_required ? <span className="badge status-active">Required</span> : <span style={{ color: '#ccc', fontSize: '0.8rem' }}>Optional</span>}</td>
                      <td style={{ fontSize: '0.78rem', color: '#888' }}>{f.placeholder || '—'}</td>
                      <td>{f.is_active ? <span className="badge status-active">Active</span> : <span className="badge status-inactive">Inactive</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Call Dispositions */}
      {tab === 'dispositions' && (
        <div>
          {dispQ.isLoading ? <Spinner /> : (
            <div className="card" style={{ overflowX: 'auto' }}>
              <div className="px-4 py-3 border-b-2 border-black" style={{ background: '#171e19' }}>
                <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.9rem' }}>▸ Call Dispositions</span>
              </div>
              {(dispQ.data ?? []).length === 0 ? (
                <div style={{ padding: '24px', textAlign: 'center', color: '#888', fontSize: '0.82rem' }}>
                  No dispositions found. Run: <code className="font-mono" style={{ background: '#f0f0f0', padding: '2px 6px' }}>python manage.py seed_dispositions --all</code>
                </div>
              ) : (
                <table className="table-brutal">
                  <thead><tr>{['Disposition', 'Slug', 'Type', 'Auto Follow-up After', 'Status'].map(h => <th key={h}>{h}</th>)}</tr></thead>
                  <tbody>
                    {(dispQ.data ?? []).map(d => (
                      <tr key={d.id}>
                        <td className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{d.name}</td>
                        <td className="font-mono" style={{ fontSize: '0.72rem', color: '#555' }}>{d.slug}</td>
                        <td>{d.is_positive ? <span className="badge status-active">Positive</span> : <span className="badge status-inactive">Negative</span>}</td>
                        <td style={{ fontSize: '0.8rem' }}>{d.auto_followup_hours ? `${d.auto_followup_hours} hours` : '—'}</td>
                        <td><span className="badge status-active">Active</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>
      )}

      {/* Teams */}
      {tab === 'teams' && (
        <div>
          {teamsQ.isLoading ? <Spinner /> : (teamsQ.data?.results ?? []).length === 0 ? (
            <EmptyState icon="◉" title="No teams" message="Teams help you organize agents into groups. Create teams via the Django admin panel or API." />
          ) : (
            <div className="grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))' }}>
              {(teamsQ.data?.results ?? []).map(t => (
                <div key={t.id} className="card p-4">
                  <div className="font-heading font-black" style={{ fontSize: '0.95rem', marginBottom: '4px' }}>{t.name}</div>
                  {t.description && <p style={{ fontSize: '0.78rem', color: '#666', marginBottom: '8px' }}>{t.description}</p>}
                  <span className="tag">{t.member_count} member{t.member_count !== 1 ? 's' : ''}</span>
                  <div style={{ marginTop: '8px' }}>
                    {t.is_active ? <span className="badge status-active">Active</span> : <span className="badge status-inactive">Inactive</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Billing */}
      {tab === 'billing' && (
        <div className="card p-5" style={{ maxWidth: '520px' }}>
          <div className="font-heading font-black mb-4" style={{ fontSize: '1rem' }}>Billing & Plan</div>
          <div style={{ background: '#fffbee', border: '2px solid #ffe17c', padding: '14px', marginBottom: '16px', fontSize: '0.84rem', lineHeight: 1.6 }}>
            To manage your subscription, upgrade your plan, or download GST invoices, visit the
            {' '}<strong>Super Admin panel</strong> at <code className="font-mono" style={{ background: '#fff0a0', padding: '1px 6px' }}>/superadmin/</code>
            {' '}or contact your platform administrator.
          </div>
          <div style={{ fontSize: '0.82rem', color: '#555', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div>📧 Support: <a href="mailto:support@telecrm.in" style={{ color: '#000', fontWeight: 700 }}>support@telecrm.in</a></div>
            <div>📞 Phone: +91-1800-XXX-XXXX</div>
            <div>💬 WhatsApp: +91-XXXXXXXXXX</div>
          </div>
        </div>
      )}

      {/* Custom Field Modal */}
      {showFieldModal && (
        <Modal title="New Custom Field" onClose={() => setShowFieldModal(false)}>
          <div className="flex flex-col gap-3">
            <Input label="Field Label *" value={fieldForm.name} onChange={e => setFieldForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Property Type, Budget Range" />
            <Select label="Field Type" value={fieldForm.field_type} onChange={e => setFieldForm(p => ({ ...p, field_type: e.target.value }))}>
              {FIELD_TYPES.map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>)}
            </Select>
            <Input label="Placeholder Text" value={fieldForm.placeholder} onChange={e => setFieldForm(p => ({ ...p, placeholder: e.target.value }))} placeholder="e.g. Enter property type…" />
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={fieldForm.is_required} onChange={e => setFieldForm(p => ({ ...p, is_required: e.target.checked }))} style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Required field (agents must fill this)</span>
            </label>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setShowFieldModal(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => createFieldMut.mutate()} disabled={createFieldMut.isPending || !fieldForm.name}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              {createFieldMut.isPending ? '◌ Creating…' : 'Create Field →'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
