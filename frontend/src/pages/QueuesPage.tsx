import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { queuesApi, authApi } from '../api';
import {
  SectionHeader, Modal, Input, Select, Textarea, ConfirmDialog,
  Spinner, EmptyState, useToast,
} from '../components/ui';
import { LEAD_STATUSES, LEAD_SOURCES } from '../utils/fmt';
import type { CallQueue } from '../types';

// Backend priority values are hot / warm / cold
const QUEUE_PRIORITIES = [
  { value: 'hot', label: '🔥 Hot' },
  { value: 'warm', label: 'Warm' },
  { value: 'cold', label: 'Cold' },
];

const ORDER_OPTIONS = [
  { value: 'priority', label: 'Highest priority first' },
  { value: 'oldest', label: 'Oldest leads first' },
  { value: 'newest', label: 'Newest leads first' },
  { value: 'score', label: 'Highest score first' },
  { value: 'followup_due', label: 'Follow-up due first' },
];

type QueueForm = {
  id?: number;
  name: string;
  description: string;
  is_active: boolean;
  filter_statuses: string[];
  filter_priorities: string[];
  filter_sources: string[];
  only_unworked: boolean;
  only_followup_due: boolean;
  exclude_dnd: boolean;
  order_by: string;
  mode: string;
  redial_cooldown_hours: number;
  lock_ttl_minutes: number;
  agent_ids: number[];
};

const EMPTY_FORM: QueueForm = {
  name: '', description: '', is_active: true,
  filter_statuses: [], filter_priorities: [], filter_sources: [],
  only_unworked: false, only_followup_due: false, exclude_dnd: true,
  order_by: 'priority', mode: 'manual',
  redial_cooldown_hours: 24, lock_ttl_minutes: 30,
  agent_ids: [],
};

export default function Queues() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<QueueForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const { data: queues, isLoading } = useQuery({
    queryKey: ['queues'],
    queryFn: () => queuesApi.list().then(r => r.data),
  });

  const { data: agentsData } = useQuery({
    queryKey: ['agents-for-queue'],
    queryFn: () => authApi.listAgents({ page_size: 100 }).then(r => r.data),
  });
  const agents = agentsData?.results ?? [];

  const saveMut = useMutation({
    mutationFn: () => {
      const { id, ...payload } = form;
      return id ? queuesApi.update(id, payload) : queuesApi.create(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queues'] });
      setShowModal(false);
      setForm(EMPTY_FORM);
      showToast('success', 'Queue saved', '');
    },
    onError: (e: unknown) =>
      showToast('error', 'Error', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Failed to save queue'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => queuesApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queues'] });
      setConfirmDelete(null);
      showToast('info', 'Queue deleted', '');
    },
  });

  const openCreate = () => { setForm(EMPTY_FORM); setShowModal(true); };
  const openEdit = (q: CallQueue) => {
    setForm({
      id: q.id,
      name: q.name, description: q.description, is_active: q.is_active,
      filter_statuses: q.filter_statuses ?? [],
      filter_priorities: q.filter_priorities ?? [],
      filter_sources: q.filter_sources ?? [],
      only_unworked: q.only_unworked, only_followup_due: q.only_followup_due,
      exclude_dnd: q.exclude_dnd, order_by: q.order_by, mode: q.mode,
      redial_cooldown_hours: q.redial_cooldown_hours, lock_ttl_minutes: q.lock_ttl_minutes,
      agent_ids: q.agents.map(a => a.id),
    });
    setShowModal(true);
  };

  const toggleIn = (key: 'filter_statuses' | 'filter_priorities' | 'filter_sources' | 'agent_ids', value: string | number) =>
    setForm(p => {
      const arr = p[key] as (string | number)[];
      const next = arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value];
      return { ...p, [key]: next };
    });

  const Chip = ({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) => (
    <button type="button" onClick={onClick}
            className="font-heading font-bold"
            style={{
              fontSize: '0.72rem', padding: '5px 10px', cursor: 'pointer',
              border: '2px solid #000', background: active ? '#ffe17c' : '#fff',
              boxShadow: active ? '2px 2px 0 #000' : 'none',
            }}>
      {label}
    </button>
  );

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Call Queues" sub={`${queues?.length ?? 0} queues`}>
        <button onClick={openCreate}
                className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          + New Queue
        </button>
      </SectionHeader>

      {isLoading ? <Spinner /> : (queues?.length ?? 0) === 0 ? (
        <EmptyState icon="▤" title="No queues yet"
                    message="Create a calling queue and assign agents. Agents pull leads one at a time — no lead is ever served to two agents or repeated."
                    action={{ label: '+ New Queue', onClick: openCreate }} />
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))' }}>
          {(queues ?? []).map(q => (
            <div key={q.id} className="card p-4" style={{ opacity: q.is_active ? 1 : 0.6 }}>
              <div className="flex items-start justify-between mb-2">
                <div className="font-heading font-black" style={{ fontSize: '1rem' }}>{q.name}</div>
                <span className="tag" style={{ background: q.mode === 'auto' ? '#fef3c7' : '#e0f2fe' }}>
                  {q.mode === 'auto' ? '⚡ Auto' : 'Manual'}
                </span>
              </div>
              {q.description && <p style={{ fontSize: '0.78rem', color: '#666', marginBottom: '8px' }}>{q.description}</p>}
              <div className="flex flex-wrap gap-1 mb-3">
                {q.filter_statuses.map(s => <span key={s} className="tag" style={{ fontSize: '0.66rem' }}>{s}</span>)}
                {q.filter_priorities.map(p => <span key={p} className="tag" style={{ fontSize: '0.66rem', background: '#ffe17c' }}>{p}</span>)}
                {q.only_unworked && <span className="tag" style={{ fontSize: '0.66rem', background: '#dcfce7' }}>fresh only</span>}
                {q.only_followup_due && <span className="tag" style={{ fontSize: '0.66rem', background: '#fee2e2' }}>f/u due</span>}
              </div>
              <div style={{ fontSize: '0.72rem', color: '#888', marginBottom: '4px' }}>
                {q.agents.length} agent{q.agents.length === 1 ? '' : 's'} · cooldown {q.redial_cooldown_hours}h · lock {q.lock_ttl_minutes}m
              </div>
              <div style={{ fontSize: '0.72rem', color: '#555', marginBottom: '10px' }}>
                {q.agents.slice(0, 4).map(a => a.name).join(', ')}{q.agents.length > 4 ? ` +${q.agents.length - 4}` : ''}
              </div>
              <div className="flex gap-2">
                <button onClick={() => openEdit(q)}
                        className="btn-brutal btn-yellow px-3 py-1.5 font-heading font-bold" style={{ fontSize: '0.72rem' }}>
                  Edit
                </button>
                <button onClick={() => setConfirmDelete(q.id)}
                        className="btn-brutal btn-danger px-3 py-1.5 font-heading font-bold" style={{ fontSize: '0.72rem' }}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showModal && (
        <Modal title={form.id ? `Edit Queue: ${form.name}` : 'New Call Queue'} onClose={() => { setShowModal(false); setForm(EMPTY_FORM); }} maxWidth="640px">
          <div className="flex flex-col gap-4">
            <Input label="Queue Name *" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Hot New Leads" />
            <Textarea label="Description" value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} placeholder="What this queue is for…" />

            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Statuses (any)</label>
              <div className="flex flex-wrap gap-2">
                {LEAD_STATUSES.map(s => <Chip key={s.value} label={s.label} active={form.filter_statuses.includes(s.value)} onClick={() => toggleIn('filter_statuses', s.value)} />)}
              </div>
            </div>

            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Priorities (any)</label>
              <div className="flex flex-wrap gap-2">
                {QUEUE_PRIORITIES.map(p => <Chip key={p.value} label={p.label} active={form.filter_priorities.includes(p.value)} onClick={() => toggleIn('filter_priorities', p.value)} />)}
              </div>
            </div>

            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Sources (any)</label>
              <div className="flex flex-wrap gap-2">
                {LEAD_SOURCES.map(s => <Chip key={s.value} label={s.label} active={form.filter_sources.includes(s.value)} onClick={() => toggleIn('filter_sources', s.value)} />)}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Select label="Order By" value={form.order_by} onChange={e => setForm(p => ({ ...p, order_by: e.target.value }))}>
                {ORDER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Select label="Mode" value={form.mode} onChange={e => setForm(p => ({ ...p, mode: e.target.value }))}>
                <option value="manual">Manual pull</option>
                <option value="auto">Auto / power-dialer</option>
              </Select>
              <Input label="Redial cooldown (hours)" type="number" value={form.redial_cooldown_hours} onChange={e => setForm(p => ({ ...p, redial_cooldown_hours: Number(e.target.value) }))} />
              <Input label="Lock TTL (minutes)" type="number" value={form.lock_ttl_minutes} onChange={e => setForm(p => ({ ...p, lock_ttl_minutes: Number(e.target.value) }))} />
            </div>

            <div className="flex flex-col gap-2">
              {[
                { k: 'only_unworked', label: 'Only fresh leads (never worked before)' },
                { k: 'only_followup_due', label: 'Only leads with a follow-up due' },
                { k: 'exclude_dnd', label: 'Skip DND (Do Not Disturb) numbers' },
                { k: 'is_active', label: 'Queue is active' },
              ].map(opt => (
                <label key={opt.k} className="flex items-center gap-2 cursor-pointer" style={{ fontSize: '0.82rem' }}>
                  <input type="checkbox" checked={form[opt.k as keyof QueueForm] as boolean}
                         onChange={e => setForm(p => ({ ...p, [opt.k]: e.target.checked }))}
                         style={{ width: '16px', height: '16px', accentColor: '#ffe17c' }} />
                  <span className="font-medium">{opt.label}</span>
                </label>
              ))}
            </div>

            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Assigned Agents *</label>
              <div className="flex flex-wrap gap-2" style={{ maxHeight: '160px', overflowY: 'auto' }}>
                {agents.map(a => <Chip key={a.id} label={`${a.name} (${a.role_display})`} active={form.agent_ids.includes(a.id)} onClick={() => toggleIn('agent_ids', a.id)} />)}
              </div>
              {agents.length === 0 && <div style={{ fontSize: '0.75rem', color: '#888' }}>No agents found.</div>}
            </div>
          </div>

          <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
            <button onClick={() => { setShowModal(false); setForm(EMPTY_FORM); }} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => saveMut.mutate()}
                    disabled={saveMut.isPending || !form.name || form.agent_ids.length === 0}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              {saveMut.isPending ? '◌ Saving…' : form.id ? 'Save Changes →' : 'Create Queue →'}
            </button>
          </div>
        </Modal>
      )}

      {confirmDelete !== null && (
        <ConfirmDialog
          title="Delete Queue?"
          message="Agents will no longer be able to pull leads from this queue. Leads themselves are not affected."
          confirmLabel="Delete"
          danger
          onConfirm={() => deleteMut.mutate(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}
