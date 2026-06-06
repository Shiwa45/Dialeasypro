import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { commsApi } from '../api';
import {
  SectionHeader, Modal, Input, Select, Textarea, Spinner,
  EmptyState, ConfirmDialog, StatusBadge, useToast,
} from '../components/ui';
import { fmtDate, fmtDateTime } from '../utils/fmt';

export default function Campaigns() {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [confirmLaunch, setConfirmLaunch] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', channel: 'whatsapp', email_subject: '', email_body: '', sms_text: '', sms_sender_id: '' });
  const [selectedTemplate, setSelectedTemplate] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['campaigns'],
    queryFn: () => commsApi.listCampaigns().then(r => r.data),
    refetchInterval: 5000,
  });

  const { data: templates } = useQuery({
    queryKey: ['wa-templates-approved'],
    queryFn: () => commsApi.listTemplates(true).then(r => r.data),
  });

  const createMut = useMutation({
    mutationFn: () =>
      commsApi.createCampaign({
        ...form,
        template: selectedTemplate ? Number(selectedTemplate) : null,
        audience_filters: {},
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] });
      setShowCreate(false);
      setForm({ name: '', channel: 'whatsapp', email_subject: '', email_body: '', sms_text: '', sms_sender_id: '' });
      setSelectedTemplate('');
      showToast('success', 'Campaign created', 'Launch it when ready.');
    },
    onError: () => showToast('error', 'Error', 'Could not create campaign.'),
  });

  const launchMut = useMutation({
    mutationFn: (id: string) => commsApi.launchCampaign(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] });
      setConfirmLaunch(null);
      showToast('success', 'Campaign launched!', 'Messages are being sent to leads.');
    },
    onError: () => showToast('error', 'Launch failed', 'Check campaign configuration.'),
  });

  const pauseMut = useMutation({
    mutationFn: (id: string) => commsApi.pauseCampaign(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['campaigns'] });
      showToast('info', 'Campaign paused', '');
    },
  });

  const f = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(p => ({ ...p, [k]: e.target.value }));

  const campaigns = data?.results ?? [];
  const BG: Record<string, string> = {
    draft: '#fff', scheduled: '#fef9c3', running: '#dcfce7',
    completed: '#d1fae5', failed: '#fee2e2', paused: '#fef3c7', cancelled: '#f3f4f6',
  };
  const CHANNEL_ICON: Record<string, string> = { whatsapp: '✉', email: '📧', sms: '📱' };

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Bulk Campaigns" sub={`${campaigns.length} campaigns`}>
        <button onClick={() => setShowCreate(true)}
                className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          + New Campaign
        </button>
      </SectionHeader>

      {isLoading ? <Spinner /> : campaigns.length === 0 ? (
        <EmptyState icon="▣" title="No campaigns" message="Create a bulk WhatsApp, Email, or SMS campaign to reach multiple leads at once."
                    action={{ label: '+ New Campaign', onClick: () => setShowCreate(true) }} />
      ) : (
        <div className="flex flex-col gap-3">
          {campaigns.map(c => (
            <div key={c.id} className="card p-4" style={{ background: BG[c.status] ?? '#fff' }}>
              <div className="flex items-start justify-between flex-wrap gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span style={{ fontSize: '1.1rem' }}>{CHANNEL_ICON[c.channel] ?? '✉'}</span>
                    <span className="font-heading font-black" style={{ fontSize: '1rem' }}>{c.name}</span>
                    <span className="tag">{c.channel.toUpperCase()}</span>
                    <StatusBadge status={c.status} />
                  </div>
                  <div className="flex gap-4 flex-wrap" style={{ fontSize: '0.78rem', color: '#555', marginBottom: '8px' }}>
                    <span>Estimated: <strong>{c.estimated_recipients}</strong></span>
                    {c.total_recipients > 0 && <span>Total: <strong>{c.total_recipients}</strong></span>}
                    {c.sent_count > 0 && <span style={{ color: '#22c55e' }}>Sent: <strong>{c.sent_count}</strong></span>}
                    {c.delivered_count > 0 && <span>Delivered: <strong>{c.delivered_count}</strong></span>}
                    {c.failed_count > 0 && <span style={{ color: '#ef4444' }}>Failed: <strong>{c.failed_count}</strong></span>}
                    {c.replied_count > 0 && <span style={{ color: '#3b82f6' }}>Replied: <strong>{c.replied_count}</strong></span>}
                    {c.delivery_rate > 0 && <span style={{ fontWeight: 700 }}>Rate: {c.delivery_rate}%</span>}
                  </div>
                  {c.status === 'running' && c.total_recipients > 0 && (
                    <div className="progress-bar" style={{ width: '200px', marginBottom: '6px' }}>
                      <div className="progress-fill" style={{ width: `${c.progress_percent}%` }} />
                    </div>
                  )}
                  {c.scheduled_at && c.status === 'scheduled' && (
                    <div style={{ fontSize: '0.72rem', color: '#888' }}>⏰ Scheduled: {fmtDateTime(c.scheduled_at)}</div>
                  )}
                  {c.completed_at && (
                    <div style={{ fontSize: '0.72rem', color: '#888' }}>✓ Completed: {fmtDateTime(c.completed_at)}</div>
                  )}
                </div>
                <div className="flex gap-2 flex-wrap items-start">
                  {c.status === 'draft' && (
                    <button onClick={() => setConfirmLaunch(c.id)}
                            className="btn-brutal btn-primary px-3 py-1.5 font-heading font-black" style={{ fontSize: '0.75rem' }}>
                      ▶ Launch
                    </button>
                  )}
                  {c.status === 'running' && (
                    <button onClick={() => pauseMut.mutate(c.id)}
                            className="btn-brutal btn-yellow px-3 py-1.5 font-heading font-black" style={{ fontSize: '0.75rem' }}>
                      ⏸ Pause
                    </button>
                  )}
                  {c.status === 'paused' && (
                    <button onClick={() => setConfirmLaunch(c.id)}
                            className="btn-brutal btn-primary px-3 py-1.5 font-heading font-black" style={{ fontSize: '0.75rem' }}>
                      ▶ Resume
                    </button>
                  )}
                  <span style={{ fontSize: '0.7rem', color: '#888', alignSelf: 'center' }}>{fmtDate(c.created_at)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <Modal title="New Bulk Campaign" onClose={() => setShowCreate(false)} maxWidth="580px">
          <div className="flex flex-col gap-3">
            <Input label="Campaign Name *" value={form.name} onChange={f('name')} placeholder="e.g. Diwali Offer 2024" />
            <Select label="Channel *" value={form.channel} onChange={f('channel')}>
              <option value="whatsapp">✉ WhatsApp</option>
              <option value="email">📧 Email</option>
              <option value="sms">📱 SMS</option>
            </Select>
            {form.channel === 'whatsapp' && (
              <Select label="WhatsApp Template (required)" value={selectedTemplate} onChange={e => setSelectedTemplate(e.target.value)}>
                <option value="">Select approved template…</option>
                {(templates ?? []).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            )}
            {form.channel === 'email' && (
              <>
                <Input label="Email Subject *" value={form.email_subject} onChange={f('email_subject')} />
                <Textarea label="Email Body *" value={form.email_body} onChange={f('email_body')} />
              </>
            )}
            {form.channel === 'sms' && (
              <>
                <Input label="Sender ID (TRAI approved)" value={form.sms_sender_id} onChange={f('sms_sender_id')} placeholder="TELCRM" />
                <Textarea label="SMS Text *" value={form.sms_text} onChange={f('sms_text')} placeholder="Max 160 characters per SMS" />
                {form.sms_text.length > 0 && (
                  <div style={{ fontSize: '0.72rem', color: form.sms_text.length > 160 ? '#ef4444' : '#888' }}>
                    {form.sms_text.length}/160 chars — DND-registered numbers will be skipped automatically.
                  </div>
                )}
              </>
            )}
            <div style={{ fontSize: '0.75rem', color: '#666', background: '#fffbee', border: '2px solid #ffe17c', padding: '10px' }}>
              ℹ <strong>Audience:</strong> All active leads. Advanced audience filters (by city, status, source) coming soon.
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setShowCreate(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => createMut.mutate()} disabled={createMut.isPending || !form.name}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              {createMut.isPending ? '◌ Creating…' : 'Create Campaign →'}
            </button>
          </div>
        </Modal>
      )}

      {confirmLaunch && (
        <ConfirmDialog
          title="Launch Campaign?"
          message="This will immediately start sending messages to all target leads. This cannot be easily undone."
          confirmLabel="Launch Now →"
          onConfirm={() => launchMut.mutate(confirmLaunch)}
          onCancel={() => setConfirmLaunch(null)}
        />
      )}
    </div>
  );
}
