// LeadFormModal.tsx — Create / Edit lead
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { leadsApi } from '../api';
import { Modal, Input, Select, Textarea } from '../components/ui';
import { LEAD_STATUSES, LEAD_PRIORITIES, LEAD_SOURCES } from '../utils/fmt';
import type { Lead } from '../types';

interface Props {
  lead?: Lead;
  onClose: () => void;
  onSuccess: () => void;
}

export default function LeadFormModal({ lead, onClose, onSuccess }: Props) {
  const isEdit = !!lead;
  const [form, setForm] = useState({
    name: lead?.name ?? '',
    phone: lead?.phone ?? '',
    alternate_phone: lead?.alternate_phone ?? '',
    email: lead?.email ?? '',
    city: lead?.city ?? '',
    state: lead?.state ?? '',
    source: lead?.source ?? 'manual',
    status: lead?.status ?? 'new',
    priority: lead?.priority ?? 'medium',
    requirement: lead?.requirement ?? '',
    budget: lead?.budget ?? '',
    deal_value: lead?.deal_value ?? '',
    tags: (lead?.tags ?? []).join(', '),
  });

  const mut = useMutation({
    mutationFn: () => {
      const payload = { ...form, tags: form.tags ? form.tags.split(',').map(t => t.trim()).filter(Boolean) : [] };
      return isEdit ? leadsApi.update(lead!.id, payload) : leadsApi.create(payload);
    },
    onSuccess,
  });

  const f = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(p => ({ ...p, [k]: e.target.value }));

  return (
    <Modal title={isEdit ? `Edit: ${lead!.name}` : 'New Lead'} onClose={onClose} maxWidth="620px">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2"><Input label="Full Name *" value={form.name} onChange={f('name')} placeholder="Rahul Sharma" /></div>
        <Input label="Phone *" value={form.phone} onChange={f('phone')} placeholder="+919876543210" />
        <Input label="Alternate Phone" value={form.alternate_phone} onChange={f('alternate_phone')} />
        <Input label="Email" type="email" value={form.email} onChange={f('email')} />
        <Input label="City" value={form.city} onChange={f('city')} />
        <Select label="Source" value={form.source} onChange={f('source')}>
          {LEAD_SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </Select>
        <Select label="Status" value={form.status} onChange={f('status')}>
          {LEAD_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </Select>
        <Select label="Priority" value={form.priority} onChange={f('priority')}>
          {LEAD_PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </Select>
        <Input label="Budget (₹)" type="number" value={form.budget} onChange={f('budget')} />
        <Input label="Deal Value (₹)" type="number" value={form.deal_value} onChange={f('deal_value')} />
        <div className="col-span-2">
          <Textarea label="Requirement" value={form.requirement} onChange={f('requirement')} placeholder="What is the lead looking for?" />
        </div>
        <div className="col-span-2">
          <Input label="Tags (comma-separated)" value={form.tags} onChange={f('tags')} placeholder="hot, referral, realty" />
        </div>
      </div>
      {mut.error && (
        <div style={{ background: '#fee2e2', border: '2px solid #ef4444', padding: '8px 12px', fontSize: '0.8rem', marginTop: '12px' }}>
          {(mut.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'An error occurred.'}
        </div>
      )}
      <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
        <button onClick={onClose} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black" style={{ fontSize: '0.85rem' }}>Cancel</button>
        <button onClick={() => mut.mutate()} disabled={mut.isPending || !form.name || !form.phone}
                className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          {mut.isPending ? '◌ Saving…' : isEdit ? 'Save Changes →' : 'Create Lead →'}
        </button>
      </div>
    </Modal>
  );
}
