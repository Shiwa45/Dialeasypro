import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { commsApi } from '../api';
import {
  SectionHeader, Modal, Input, Select, Textarea, Spinner, EmptyState,
  StatusBadge, useToast,
} from '../components/ui';
import { LEAD_SOURCES } from '../utils/fmt';

export default function Communications() {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<'templates' | 'send'>('templates');
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [tplForm, setTplForm] = useState({ name: '', category: 'marketing', body_text: '', language: 'en', provider: 'interakt' });
  const [sendForm, setSendForm] = useState({ lead_id: '', channel: 'whatsapp', message: '', template_id: '', sender_id: '' });

  const { data: templates, isLoading } = useQuery({
    queryKey: ['wa-templates'],
    queryFn: () => commsApi.listTemplates().then(r => r.data),
  });

  const createTplMut = useMutation({
    mutationFn: () => commsApi.createTemplate(tplForm),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wa-templates'] });
      setShowTemplateModal(false);
      setTplForm({ name: '', category: 'marketing', body_text: '', language: 'en', provider: 'interakt' });
      showToast('success', 'Template created', 'Submit it to Meta for approval to use in bulk campaigns.');
    },
    onError: () => showToast('error', 'Error', 'Could not create template.'),
  });

  const sendMut = useMutation({
    mutationFn: () =>
      sendForm.channel === 'whatsapp'
        ? commsApi.sendWhatsApp(Number(sendForm.lead_id), sendForm.message, sendForm.template_id ? Number(sendForm.template_id) : undefined)
        : commsApi.sendSMS(Number(sendForm.lead_id), sendForm.message, sendForm.sender_id),
    onSuccess: () => {
      setSendForm(p => ({ ...p, message: '', lead_id: '' }));
      showToast('success', 'Message queued', 'It will be delivered shortly.');
    },
    onError: (e: unknown) => showToast('error', 'Send failed', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Check lead ID and configuration.'),
  });

  const tf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setTplForm(p => ({ ...p, [k]: e.target.value }));
  const sf = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setSendForm(p => ({ ...p, [k]: e.target.value }));

  const STATUS_COLORS: Record<string, string> = {
    approved: '#dcfce7', pending: '#fef9c3', rejected: '#fee2e2', paused: '#f3f4f6',
  };

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Communications" sub="WhatsApp, Email & SMS">
        {tab === 'templates' && (
          <button onClick={() => setShowTemplateModal(true)}
                  className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                  style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
            + New Template
          </button>
        )}
      </SectionHeader>

      <div style={{ display: 'flex', borderBottom: '2px solid #000' }}>
        {(['templates', 'send'] as const).map((t, i) => (
          <button key={t} onClick={() => setTab(t)} className="font-heading font-bold px-5 py-2.5"
                  style={{ background: tab === t ? '#ffe17c' : '#fff', border: 'none', borderRight: '2px solid #000', cursor: 'pointer', fontSize: '0.82rem' }}>
            {t === 'templates' ? '▦ Message Templates' : '✉ Send Single Message'}
          </button>
        ))}
      </div>

      {tab === 'templates' && (
        isLoading ? <Spinner /> : (templates ?? []).length === 0 ? (
          <EmptyState icon="✉" title="No templates yet"
                      message="Create WhatsApp templates. They need Meta approval before use in bulk campaigns."
                      action={{ label: '+ New Template', onClick: () => setShowTemplateModal(true) }} />
        ) : (
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))' }}>
            {(templates ?? []).map(t => (
              <div key={t.id} className="card p-4" style={{ background: STATUS_COLORS[t.status] ?? '#fff' }}>
                <div className="flex items-start justify-between mb-2">
                  <div className="font-heading font-black" style={{ fontSize: '0.95rem' }}>{t.name}</div>
                  <StatusBadge status={t.status} />
                </div>
                <div className="flex gap-1 flex-wrap mb-2">
                  <span className="tag">{t.category}</span>
                  <span className="tag">{t.language.toUpperCase()}</span>
                  <span className="tag">{t.provider}</span>
                </div>
                <p style={{ fontSize: '0.82rem', color: '#555', lineHeight: 1.5, background: 'rgba(255,255,255,0.6)', padding: '8px', border: '1px solid #e5e5e5' }}>
                  {t.body_text}
                </p>
                {t.header_text && (
                  <div style={{ fontSize: '0.72rem', color: '#888', marginTop: '6px' }}>Header: {t.header_text}</div>
                )}
                <div style={{ fontSize: '0.7rem', color: '#888', marginTop: '6px' }}>
                  Used {t.usage_count} times
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {tab === 'send' && (
        <div className="card p-5" style={{ maxWidth: '520px' }}>
          <div className="font-heading font-black mb-4" style={{ fontSize: '0.95rem' }}>Send Single Message</div>
          <div className="flex flex-col gap-3">
            <Input label="Lead ID *" value={sendForm.lead_id} onChange={sf('lead_id')} placeholder="Enter lead ID" type="number" />
            <Select label="Channel" value={sendForm.channel} onChange={sf('channel')}>
              <option value="whatsapp">✉ WhatsApp</option>
              <option value="sms">📱 SMS</option>
            </Select>
            {sendForm.channel === 'whatsapp' && (
              <Select label="Template (optional)" value={sendForm.template_id} onChange={sf('template_id')}>
                <option value="">No template — type custom message</option>
                {(templates ?? []).filter(t => t.status === 'approved').map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </Select>
            )}
            {sendForm.channel === 'sms' && (
              <Input label="Sender ID" value={sendForm.sender_id} onChange={sf('sender_id')} placeholder="TELCRM (max 6 chars, TRAI approved)" />
            )}
            <Textarea label="Message *" value={sendForm.message} onChange={sf('message')} placeholder="Type your message here…" />
            {sendForm.channel === 'sms' && sendForm.message.length > 0 && (
              <div style={{ fontSize: '0.72rem', color: sendForm.message.length > 160 ? '#ef4444' : '#888' }}>
                {sendForm.message.length}/160 chars ({Math.ceil(sendForm.message.length / 160)} SMS)
              </div>
            )}
            <button
              onClick={() => sendMut.mutate()}
              disabled={!sendForm.lead_id || (!sendForm.message && !sendForm.template_id) || sendMut.isPending}
              className="btn-brutal btn-primary py-2.5 font-heading font-black"
              style={{ fontSize: '0.88rem', boxShadow: '5px 5px 0 #000' }}
            >
              {sendMut.isPending ? '◌ Sending…' : 'Send Message →'}
            </button>
          </div>
        </div>
      )}

      {showTemplateModal && (
        <Modal title="New WhatsApp Template" onClose={() => setShowTemplateModal(false)}>
          <div className="flex flex-col gap-3">
            <Input label="Template Name *" value={tplForm.name} onChange={tf('name')} placeholder="e.g. welcome_followup" />
            <Select label="Category" value={tplForm.category} onChange={tf('category')}>
              <option value="marketing">Marketing</option>
              <option value="utility">Utility / Transactional</option>
              <option value="authentication">Authentication (OTP)</option>
            </Select>
            <Select label="Provider" value={tplForm.provider} onChange={tf('provider')}>
              <option value="interakt">Interakt</option>
              <option value="aisensy">AiSensy</option>
              <option value="wati">Wati</option>
              <option value="gupshup">Gupshup</option>
            </Select>
            <Select label="Language" value={tplForm.language} onChange={tf('language')}>
              <option value="en">English</option>
              <option value="hi">Hindi (हिन्दी)</option>
              <option value="mr">Marathi (मराठी)</option>
              <option value="gu">Gujarati (ગુજરાતી)</option>
              <option value="ta">Tamil (தமிழ்)</option>
            </Select>
            <Textarea
              label="Body Text *"
              value={tplForm.body_text}
              onChange={tf('body_text')}
              placeholder="Hi {{1}}, your property enquiry has been received. Our agent will call you within {{2}} hours."
            />
            <div style={{ fontSize: '0.75rem', color: '#555', background: '#fffbee', border: '2px solid #ffe17c', padding: '10px' }}>
              <strong>Variable syntax:</strong> Use {'{{1}}'}, {'{{2}}'} etc. for personalization.<br />
              Map these to lead fields in the backend after creating.<br />
              Template requires Meta approval (1–3 business days) before bulk use.
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setShowTemplateModal(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => createTplMut.mutate()} disabled={createTplMut.isPending || !tplForm.name || !tplForm.body_text}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              Create Template →
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
