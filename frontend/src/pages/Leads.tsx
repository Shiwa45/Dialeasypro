import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { leadsApi, authApi } from '../api';
import {
  SectionHeader, StatusBadge, PriorityBadge, Pagination,
  Spinner, EmptyState, ConfirmDialog, Select, ScoreBar, useToast,
  Modal, Input,
} from '../components/ui';
import { fmtDate, fmtRelative, LEAD_STATUSES, LEAD_SOURCES, LEAD_PRIORITIES } from '../utils/fmt';
import { useAuthStore } from '../store/authStore';
import LeadFormModal from './LeadFormModal';

export default function Leads() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { showToast } = useToast();
  const { agent } = useAuthStore();
  const isAdmin = agent?.role?.toLowerCase() === 'admin' || agent?.is_tenant_admin === true;

  const [view, setView] = useState<'table' | 'kanban'>('table');
  const [selected, setSelected] = useState<number[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [bulkAgent, setBulkAgent] = useState('');
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [showDistribute, setShowDistribute] = useState(false);
  const [distAgents, setDistAgents] = useState<number[]>([]);
  const [distOnlyUnassigned, setDistOnlyUnassigned] = useState(true);
  const [distLimit, setDistLimit] = useState('');
  const [showFlush, setShowFlush] = useState(false);
  const [flushConfirm, setFlushConfirm] = useState('');

  const page = Number(params.get('page') ?? 1);
  const status = params.get('status') ?? '';
  const priority = params.get('priority') ?? '';
  const source = params.get('source') ?? '';
  const search = params.get('search') ?? '';
  const assigned_to = params.get('assigned_to') ?? '';
  const overdue = params.get('overdue') ?? '';

  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v); else p.delete(k);
    p.set('page', '1');
    setParams(p);
  };

  const { data, isLoading } = useQuery({
    queryKey: ['leads', page, status, priority, source, search, assigned_to, overdue],
    queryFn: () => leadsApi.list({
      page, status: status || undefined, priority: priority || undefined,
      source: source || undefined, search: search || undefined,
      assigned_to: assigned_to || undefined, overdue: overdue || undefined,
      page_size: 25,
    }).then(r => r.data),
    placeholderData: prev => prev,
  });

  const { data: pipelineData } = useQuery({
    queryKey: ['leads-pipeline'],
    queryFn: () => leadsApi.pipeline().then(r => r.data),
    enabled: view === 'kanban',
  });

  // Agents list for the bulk-assign dropdown (admin/manager only endpoint)
  const { data: agentsData } = useQuery({
    queryKey: ['agents-for-assign'],
    queryFn: () => authApi.listAgents({ page_size: 100 }).then(r => r.data),
  });
  const agents = agentsData?.results ?? [];

  const deleteMut = useMutation({
    mutationFn: (id: number) => leadsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      showToast('success', 'Lead deleted', 'Lead has been removed.');
      setConfirmDelete(null);
    },
  });

  const bulkAssignMut = useMutation({
    mutationFn: () => leadsApi.bulkAssign(selected, Number(bulkAgent)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      showToast('success', `${selected.length} leads assigned`, '');
      setSelected([]);
      setBulkAgent('');
    },
  });

  const statusMut = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) => leadsApi.updateStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['leads-pipeline'] }),
  });

  const distributeMut = useMutation({
    mutationFn: () => leadsApi.distribute({
      agent_ids: distAgents,
      only_unassigned: distOnlyUnassigned,
      statuses: status ? [status] : [],
      priorities: priority ? [priority] : [],
      sources: source ? [source] : [],
      search: search || undefined,
      limit: distLimit ? Number(distLimit) : null,
    }).then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      if (data.distributed === 0) {
        showToast('info', 'No leads matched', data.message ?? 'Adjust filters and try again.');
      } else {
        const summary = Object.entries(data.per_agent).map(([n, c]) => `${n}: ${c}`).join(', ');
        showToast('success', `${data.distributed} leads distributed`, summary);
      }
      setShowDistribute(false);
      setDistAgents([]);
      setDistLimit('');
    },
    onError: (e: unknown) =>
      showToast('error', 'Distribution failed', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Please try again.'),
  });

  const flushMut = useMutation({
    mutationFn: () => leadsApi.flush(flushConfirm).then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: ['leads-pipeline'] });
      showToast('success', 'Leads flushed', `${data.deleted} leads permanently deleted.`);
      setShowFlush(false);
      setFlushConfirm('');
    },
    onError: (e: unknown) =>
      showToast('error', 'Flush failed', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Please try again.'),
  });

  const handleExport = async () => {
    try {
      const res = await leadsApi.export({ status, source, assigned_to });
      const url = URL.createObjectURL(new Blob([res.data as BlobPart]));
      const a = document.createElement('a');
      a.href = url; a.download = `leads_${Date.now()}.csv`; a.click();
      URL.revokeObjectURL(url);
      showToast('success', 'Export started', 'CSV download has begun.');
    } catch { showToast('error', 'Export failed', 'Please try again.'); }
  };

  const PIPELINE_COLS = [
    { key: 'new', label: 'New', color: '#e0f2fe' },
    { key: 'contacted', label: 'Contacted', color: '#fef9c3' },
    { key: 'interested', label: 'Interested', color: '#dcfce7' },
    { key: 'negotiation', label: 'Negotiation', color: '#fef3c7' },
    { key: 'converted', label: 'Converted', color: '#d1fae5' },
  ];

  const leads = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Leads" sub={`${total.toLocaleString()} total`}>
        {/* View toggle */}
        <div style={{ border: '2px solid #000', display: 'flex' }}>
          {(['table','kanban'] as const).map((v, i) => (
            <button key={v} onClick={() => setView(v)}
                    className="px-3 py-2 font-heading font-bold"
                    style={{ background: view === v ? '#ffe17c' : '#fff', border: 'none', cursor: 'pointer', fontSize: '0.75rem', borderRight: i === 0 ? '2px solid #000' : 'none' }}>
              {v === 'table' ? '≡ Table' : '▦ Kanban'}
            </button>
          ))}
        </div>
        <button onClick={handleExport}
                className="btn-brutal btn-secondary px-3 py-2 font-heading font-bold"
                style={{ fontSize: '0.8rem', boxShadow: '3px 3px 0 #000' }}>↓ Export CSV</button>
        <button onClick={() => setShowDistribute(true)}
                className="btn-brutal btn-yellow px-3 py-2 font-heading font-bold"
                style={{ fontSize: '0.8rem', boxShadow: '3px 3px 0 #000' }}>⇄ Distribute</button>
        {isAdmin && (
          <button onClick={() => { setFlushConfirm(''); setShowFlush(true); }}
                  className="btn-brutal btn-danger px-3 py-2 font-heading font-bold"
                  style={{ fontSize: '0.8rem', boxShadow: '3px 3px 0 #000' }}>🗑 Flush All</button>
        )}
        <button onClick={() => setShowCreate(true)}
                className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>+ New Lead</button>
      </SectionHeader>

      {/* Filters */}
      <div className="card card-sm p-3 flex flex-wrap items-center gap-2">
        <input placeholder="Search name, phone, email…" value={search}
               onChange={e => set('search', e.target.value)}
               className="input-brutal flex-1" style={{ minWidth: '180px', boxShadow: '2px 2px 0 #000' }} />
        <select value={status} onChange={e => set('status', e.target.value)}
                className="input-brutal" style={{ width: 'auto', boxShadow: '2px 2px 0 #000' }}>
          <option value="">All Statuses</option>
          {LEAD_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={priority} onChange={e => set('priority', e.target.value)}
                className="input-brutal" style={{ width: 'auto', boxShadow: '2px 2px 0 #000' }}>
          <option value="">All Priorities</option>
          {LEAD_PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select value={source} onChange={e => set('source', e.target.value)}
                className="input-brutal" style={{ width: 'auto', boxShadow: '2px 2px 0 #000' }}>
          <option value="">All Sources</option>
          {LEAD_SOURCES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <button onClick={() => { set('overdue', overdue ? '' : 'true'); }}
                className="btn-brutal px-3 py-2 font-heading font-bold"
                style={{ fontSize: '0.75rem', background: overdue ? '#ef4444' : '#fff', color: overdue ? '#fff' : '#000', boxShadow: '2px 2px 0 #000' }}>
          ⏰ Overdue {overdue ? '✕' : ''}
        </button>
        {(status || priority || source || search || overdue || assigned_to) && (
          <button onClick={() => setParams(new URLSearchParams({ page: '1' }))}
                  className="btn-brutal btn-secondary px-3 py-2 font-heading font-bold"
                  style={{ fontSize: '0.75rem' }}>Clear Filters</button>
        )}
      </div>

      {/* Bulk actions bar */}
      {selected.length > 0 && (
        <div className="card card-sm p-3 flex items-center gap-3 flex-wrap"
             style={{ background: '#ffe17c', borderColor: '#000' }}>
          <span className="font-heading font-black" style={{ fontSize: '0.85rem' }}>{selected.length} selected</span>
          <select value={bulkAgent} onChange={e => setBulkAgent(e.target.value)}
                  className="input-brutal" style={{ width: '200px', background: '#fff', boxShadow: '2px 2px 0 #000' }}>
            <option value="">Assign to agent…</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name} ({a.role_display})</option>
            ))}
          </select>
          <button onClick={() => bulkAssignMut.mutate()}
                  disabled={!bulkAgent || bulkAssignMut.isPending}
                  className="btn-brutal btn-primary px-3 py-2 font-heading font-black" style={{ fontSize: '0.8rem' }}>
            Assign All →
          </button>
          <button onClick={() => setSelected([])}
                  className="btn-brutal btn-secondary px-3 py-2 font-heading font-bold" style={{ fontSize: '0.8rem' }}>
            Clear
          </button>
        </div>
      )}

      {isLoading ? <Spinner /> : view === 'table' ? (
        <>
          {leads.length === 0 ? (
            <EmptyState icon="◎" title="No leads found"
                        message="Try adjusting your filters or create a new lead."
                        action={{ label: '+ New Lead', onClick: () => setShowCreate(true) }} />
          ) : (
            <div className="card" style={{ overflowX: 'auto' }}>
              <table className="table-brutal">
                <thead>
                  <tr>
                    <th><input type="checkbox"
                               checked={selected.length === leads.length && leads.length > 0}
                               onChange={e => setSelected(e.target.checked ? leads.map(l => l.id) : [])} /></th>
                    {['Lead', 'Phone', 'Source', 'Status', 'Priority', 'Score', 'Assigned', 'Follow-up', 'Created', 'Actions'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {leads.map(lead => (
                    <tr key={lead.id}>
                      <td><input type="checkbox" checked={selected.includes(lead.id)}
                                 onChange={e => setSelected(p => e.target.checked ? [...p, lead.id] : p.filter(x => x !== lead.id))} /></td>
                      <td>
                        <div className="font-heading font-bold cursor-pointer" style={{ fontSize: '0.83rem' }}
                             onClick={() => nav(`/leads/${lead.id}`)}>{lead.name}</div>
                        {lead.city && <div style={{ fontSize: '0.7rem', color: '#888' }}>{lead.city}</div>}
                      </td>
                      <td className="font-mono" style={{ fontSize: '0.78rem' }}>{lead.phone}</td>
                      <td>
                        <span className="tag">{lead.source_display}</span>
                        {lead.campaign_name && (
                          <div title={lead.campaign_name} style={{ fontSize: '0.66rem', color: '#888', marginTop: '2px', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            📣 {lead.campaign_name}
                          </div>
                        )}
                      </td>
                      <td><StatusBadge status={lead.status} label={lead.status_display} /></td>
                      <td><PriorityBadge priority={lead.priority} /></td>
                      <td><ScoreBar score={lead.score} /></td>
                      <td style={{ fontSize: '0.78rem' }}>{lead.assigned_to_name ?? <span style={{ color: '#ccc' }}>Unassigned</span>}</td>
                      <td style={{ fontSize: '0.75rem' }}>
                        {lead.next_followup_at ? (
                          <span style={{ color: lead.followup_overdue ? '#ef4444' : '#333', fontWeight: lead.followup_overdue ? 700 : 400 }}>
                            {lead.followup_overdue ? '⚠ ' : ''}{fmtRelative(lead.next_followup_at)}
                          </span>
                        ) : <span style={{ color: '#ccc' }}>—</span>}
                      </td>
                      <td style={{ fontSize: '0.72rem', color: '#888' }}>{fmtDate(lead.created_at)}</td>
                      <td>
                        <div className="flex gap-1">
                          <button onClick={() => nav(`/leads/${lead.id}`)}
                                  className="btn-brutal btn-yellow px-2 py-1 font-heading font-bold" style={{ fontSize: '0.68rem' }}>View</button>
                          <button onClick={() => setConfirmDelete(lead.id)}
                                  className="btn-brutal btn-danger px-2 py-1 font-heading font-bold" style={{ fontSize: '0.68rem' }}>✕</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="px-4 pb-4">
                <Pagination page={page} totalPages={data?.total_pages ?? 1}
                            onPageChange={p => set('page', String(p))} />
              </div>
            </div>
          )}
        </>
      ) : (
        /* Kanban view */
        <div style={{ display: 'flex', gap: '16px', overflowX: 'auto', paddingBottom: '16px' }}>
          {PIPELINE_COLS.map(col => {
            const colLeads = (pipelineData?.[col.key] ?? []) as unknown[];
            return (
              <div key={col.key} className="pipeline-col">
                <div style={{ background: '#171e19', border: '2px solid #000', padding: '8px 12px', marginBottom: '8px' }}>
                  <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.82rem' }}>{col.label}</span>
                  <span style={{ color: '#b7c6c2', fontSize: '0.72rem', marginLeft: '6px' }}>({colLeads.length})</span>
                </div>
                <div className="flex flex-col gap-2">
                  {(colLeads as Array<{id:number;name:string;phone:string;city?:string;priority:string;score:number;deal_value:string|null;'assigned_to__name':string}>).map(lead => (
                    <div key={lead.id} className="card card-sm p-3 cursor-pointer"
                         style={{ background: col.color }}
                         onClick={() => nav(`/leads/${lead.id}`)}>
                      <div className="font-heading font-bold" style={{ fontSize: '0.82rem', marginBottom: '4px' }}>{lead.name}</div>
                      <div className="font-mono" style={{ fontSize: '0.7rem', color: '#555' }}>{lead.phone}</div>
                      {lead.city && <div style={{ fontSize: '0.68rem', color: '#888' }}>{lead.city}</div>}
                      <div className="flex items-center justify-between mt-2">
                        <PriorityBadge priority={lead.priority} />
                        <ScoreBar score={lead.score} />
                      </div>
                      {lead.deal_value && (
                        <div className="font-heading font-black mt-1" style={{ fontSize: '0.75rem' }}>₹{Number(lead.deal_value).toLocaleString('en-IN')}</div>
                      )}
                    </div>
                  ))}
                  {colLeads.length === 0 && (
                    <div style={{ border: '2px dashed #ccc', padding: '20px', textAlign: 'center', color: '#999', fontSize: '0.75rem' }}>No leads</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {showCreate && <LeadFormModal onClose={() => setShowCreate(false)} onSuccess={() => { qc.invalidateQueries({ queryKey: ['leads'] }); setShowCreate(false); showToast('success', 'Lead created', ''); }} />}

      {confirmDelete !== null && (
        <ConfirmDialog title="Delete Lead?" message="This lead will be permanently removed. This action cannot be undone."
                       confirmLabel="Delete" danger
                       onConfirm={() => deleteMut.mutate(confirmDelete)}
                       onCancel={() => setConfirmDelete(null)} />
      )}

      {/* Distribute modal — bulk-assign leads matching filters across agents */}
      {showDistribute && (
        <Modal title="Distribute Leads to Agents" onClose={() => setShowDistribute(false)} maxWidth="560px">
          <div className="flex flex-col gap-4">
            <div style={{ background: '#fffbee', border: '2px solid #ffe17c', padding: '10px 12px', fontSize: '0.8rem' }}>
              Distributes leads matching the <strong>current filters</strong>
              {(status || priority || source || search) ? '' : ' (no filters → all leads)'} across the
              selected agents. With multiple agents, leads are split evenly (round-robin).
            </div>

            <div style={{ fontSize: '0.78rem', color: '#555' }}>
              Active filters:&nbsp;
              {[
                status && `status=${status}`,
                priority && `priority=${priority}`,
                source && `source=${source}`,
                search && `search="${search}"`,
              ].filter(Boolean).join(', ') || 'none'}
            </div>

            <label className="flex items-center gap-2 cursor-pointer" style={{ fontSize: '0.82rem' }}>
              <input type="checkbox" checked={distOnlyUnassigned}
                     onChange={e => setDistOnlyUnassigned(e.target.checked)}
                     style={{ width: '16px', height: '16px', accentColor: '#ffe17c' }} />
              <span className="font-medium">Only distribute currently unassigned leads</span>
            </label>

            <Input label="Max leads to distribute (optional)" type="number" value={distLimit}
                   onChange={e => setDistLimit(e.target.value)} placeholder="Leave blank for all matching" />

            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>
                Distribute to agents *
              </label>
              <div className="flex flex-wrap gap-2" style={{ maxHeight: '160px', overflowY: 'auto' }}>
                {agents.map(a => {
                  const on = distAgents.includes(a.id);
                  return (
                    <button key={a.id} type="button"
                            onClick={() => setDistAgents(p => on ? p.filter(x => x !== a.id) : [...p, a.id])}
                            className="font-heading font-bold"
                            style={{ fontSize: '0.72rem', padding: '5px 10px', cursor: 'pointer',
                                     border: '2px solid #000', background: on ? '#ffe17c' : '#fff',
                                     boxShadow: on ? '2px 2px 0 #000' : 'none' }}>
                      {a.name} ({a.role_display})
                    </button>
                  );
                })}
              </div>
              {agents.length === 0 && <div style={{ fontSize: '0.75rem', color: '#888' }}>No agents found.</div>}
            </div>
          </div>

          <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
            <button onClick={() => setShowDistribute(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => distributeMut.mutate()}
                    disabled={distributeMut.isPending || distAgents.length === 0}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              {distributeMut.isPending ? '◌ Distributing…' : `Distribute → ${distAgents.length || ''} agent${distAgents.length === 1 ? '' : 's'}`}
            </button>
          </div>
        </Modal>
      )}

      {/* Flush all leads — destructive, admin only, typed confirmation */}
      {showFlush && (
        <Modal title="⚠ Flush All Leads" onClose={() => setShowFlush(false)} maxWidth="460px">
          <div className="flex flex-col gap-3">
            <div style={{ background: '#fee2e2', border: '2px solid #ef4444', padding: '12px', fontSize: '0.82rem', lineHeight: 1.5 }}>
              This <strong>permanently deletes ALL {total.toLocaleString()} leads</strong> in this
              workspace — along with their notes, follow-ups, and activity history.
              <br /><strong>This cannot be undone.</strong>
            </div>
            <div style={{ fontSize: '0.8rem', color: '#555' }}>
              Type <strong>FLUSH ALL</strong> below to confirm:
            </div>
            <Input
              label=""
              value={flushConfirm}
              onChange={e => setFlushConfirm(e.target.value)}
              placeholder="FLUSH ALL"
            />
          </div>
          <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
            <button onClick={() => setShowFlush(false)}
                    className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => flushMut.mutate()}
                    disabled={flushMut.isPending || flushConfirm.trim().toUpperCase() !== 'FLUSH ALL'}
                    className="btn-brutal btn-danger flex-1 py-2.5 font-heading font-black"
                    style={{ boxShadow: '5px 5px 0 #000' }}>
              {flushMut.isPending ? '◌ Deleting…' : 'Permanently Delete All'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
