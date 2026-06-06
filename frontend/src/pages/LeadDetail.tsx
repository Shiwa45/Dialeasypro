import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsApi, callsApi, commsApi } from '../api';
import {
  Spinner, StatusBadge, PriorityBadge, ScoreBar, Modal,
  Input, Select, Textarea, ConfirmDialog, useToast, EmptyState,
} from '../components/ui';
import { fmtDate, fmtDateTime, fmtRelative, LEAD_STATUSES } from '../utils/fmt';
import LeadFormModal from './LeadFormModal';

const TABS = ['Overview', 'Notes', 'Follow-ups', 'Activity', 'Calls', 'WhatsApp'] as const;
type Tab = (typeof TABS)[number];

export default function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { showToast } = useToast();
  const [tab, setTab] = useState<Tab>('Overview');
  const [showEdit, setShowEdit] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [showFollowupModal, setShowFollowupModal] = useState(false);
  const [followupForm, setFollowupForm] = useState({ followup_type: 'call', scheduled_at: '', notes: '' });
  const [showCallModal, setShowCallModal] = useState(false);
  const [callForm, setCallForm] = useState({ direction: 'outbound', duration_seconds: '', notes: '', disposition: '', is_connected: false });
  const [waMessage, setWaMessage] = useState('');

  const { data: lead, isLoading } = useQuery({
    queryKey: ['lead', id],
    queryFn: () => leadsApi.get(Number(id)).then(r => r.data),
    enabled: !!id,
  });
  const { data: notesData } = useQuery({
    queryKey: ['lead-notes', id],
    queryFn: () => leadsApi.listNotes(Number(id)).then(r => r.data),
    enabled: !!id && tab === 'Notes',
  });
  const { data: followupsData } = useQuery({
    queryKey: ['lead-followups', id],
    queryFn: () => leadsApi.listFollowups(Number(id)).then(r => r.data),
    enabled: !!id && (tab === 'Follow-ups' || tab === 'Overview'),
  });
  const { data: activitiesData } = useQuery({
    queryKey: ['lead-activities', id],
    queryFn: () => leadsApi.listActivities(Number(id)).then(r => r.data),
    enabled: !!id && tab === 'Activity',
  });
  const { data: callsData } = useQuery({
    queryKey: ['lead-calls', id],
    queryFn: () => callsApi.list({ lead: id }).then(r => r.data),
    enabled: !!id && tab === 'Calls',
  });
  const { data: waMessages } = useQuery({
    queryKey: ['lead-wa', id],
    queryFn: () => commsApi.listMessages(Number(id)).then(r => r.data),
    enabled: !!id && tab === 'WhatsApp',
  });
  const { data: dispositions } = useQuery({
    queryKey: ['dispositions'],
    queryFn: () => callsApi.dispositions().then(r => r.data),
  });

  const addNoteMut = useMutation({
    mutationFn: () => leadsApi.createNote(Number(id), noteText),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lead-notes', id] }); setNoteText(''); showToast('success', 'Note added', ''); },
  });
  const statusMut = useMutation({
    mutationFn: (status: string) => leadsApi.updateStatus(Number(id), status),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lead', id] }); showToast('success', 'Status updated', ''); },
  });
  const addFollowupMut = useMutation({
    mutationFn: () => leadsApi.createFollowup(Number(id), followupForm),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lead-followups', id] }); setShowFollowupModal(false); showToast('success', 'Follow-up scheduled', ''); },
  });
  const completeFuMut = useMutation({
    mutationFn: (fuId: number) => leadsApi.completeFollowup(fuId, ''),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead-followups', id] }),
  });
  const logCallMut = useMutation({
    mutationFn: () => callsApi.create({ lead: Number(id), phone_number: lead?.phone, ...callForm }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lead-calls', id] }); setShowCallModal(false); showToast('success', 'Call logged', ''); },
  });
  const sendWaMut = useMutation({
    mutationFn: () => commsApi.sendWhatsApp(Number(id), waMessage),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['lead-wa', id] }); setWaMessage(''); showToast('success', 'WhatsApp sent', ''); },
  });
  const clickToCallMut = useMutation({
    mutationFn: () => callsApi.clickToCall(Number(id)),
    onSuccess: () => showToast('success', 'Call initiated', 'Your phone will ring first.'),
    onError: () => showToast('error', 'Call failed', 'Check your calling integration settings.'),
  });

  if (isLoading || !lead) return <Spinner />;

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-medium" style={{ fontSize: '0.78rem', color: '#888' }}>
        <button onClick={() => nav('/leads')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#888' }}>Leads</button>
        <span>›</span>
        <span style={{ color: '#000', fontWeight: 700 }}>{lead.name}</span>
      </div>

      {/* Header */}
      <div className="card p-5 flex flex-wrap items-start gap-4 justify-between">
        <div className="flex items-start gap-4">
          <div style={{ width: '52px', height: '52px', background: '#b7c6c2', border: '2px solid #000', boxShadow: '3px 3px 0 #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1rem', fontFamily: 'Space Grotesk', fontWeight: 900, flexShrink: 0 }}>
            {lead.name.split(' ').map(n => n[0]).join('').slice(0,2).toUpperCase()}
          </div>
          <div>
            <h2 className="font-heading font-black" style={{ fontSize: '1.3rem' }}>{lead.name}</h2>
            <div className="flex items-center gap-2 flex-wrap mt-1">
              <StatusBadge status={lead.status} label={lead.status_display} />
              <PriorityBadge priority={lead.priority} />
              {lead.is_dnd && <span className="badge" style={{ background: '#ef4444', color: '#fff', borderColor: '#ef4444' }}>DND</span>}
              <ScoreBar score={lead.score} />
            </div>
            <div className="flex gap-4 mt-2 flex-wrap" style={{ fontSize: '0.8rem', color: '#555' }}>
              <span>☎ {lead.phone}</span>
              {lead.email && <span>✉ {lead.email}</span>}
              {lead.city && <span>📍 {lead.city}</span>}
            </div>
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => clickToCallMut.mutate()}
                  className="btn-brutal btn-primary px-3 py-2 font-heading font-black" style={{ fontSize: '0.8rem' }}>
            ☎ Call
          </button>
          <button onClick={() => setShowFollowupModal(true)}
                  className="btn-brutal btn-yellow px-3 py-2 font-heading font-black" style={{ fontSize: '0.8rem' }}>
            + Follow-up
          </button>
          <button onClick={() => setShowEdit(true)}
                  className="btn-brutal btn-secondary px-3 py-2 font-heading font-bold" style={{ fontSize: '0.8rem' }}>
            ✏ Edit
          </button>
        </div>
      </div>

      {/* Quick status change */}
      <div className="card card-sm p-3 flex items-center gap-3 flex-wrap">
        <span className="font-heading font-bold" style={{ fontSize: '0.75rem' }}>Quick Status:</span>
        {LEAD_STATUSES.map(s => (
          <button key={s.value} onClick={() => statusMut.mutate(s.value)}
                  className="btn-brutal px-2.5 py-1 font-heading font-bold"
                  style={{ fontSize: '0.68rem', background: lead.status === s.value ? '#ffe17c' : '#fff', boxShadow: '2px 2px 0 #000' }}>
            {s.label}
          </button>
        ))}
      </div>

      {/* Tabs */}
      <div>
        <div style={{ display: 'flex', borderBottom: '2px solid #000', overflowX: 'auto' }}>
          {TABS.map(t => (
            <button key={t} onClick={() => setTab(t)}
                    className="font-heading font-bold px-4 py-2.5"
                    style={{ background: tab === t ? '#ffe17c' : '#fff', border: 'none', borderRight: '2px solid #000', cursor: 'pointer', fontSize: '0.8rem', whiteSpace: 'nowrap', borderBottom: tab === t ? '2px solid #ffe17c' : 'none' }}>
              {t}
            </button>
          ))}
        </div>

        <div className="card mt-0" style={{ borderTop: 'none' }}>
          {/* Overview */}
          {tab === 'Overview' && (
            <div className="p-5">
              <div className="grid grid-cols-2 gap-x-8 gap-y-3" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
                {[
                  ['Source', lead.source_display],
                  ['Assigned To', lead.assigned_to_name ?? '—'],
                  ['Budget', lead.budget ? `₹${Number(lead.budget).toLocaleString('en-IN')}` : '—'],
                  ['Deal Value', lead.deal_value ? `₹${Number(lead.deal_value).toLocaleString('en-IN')}` : '—'],
                  ['Contact Count', lead.contact_count],
                  ['Last Contacted', fmtRelative(lead.last_contacted_at)],
                  ['Next Follow-up', lead.next_followup_at ? fmtDateTime(lead.next_followup_at) : '—'],
                  ['Created', fmtDate(lead.created_at)],
                  ['Phone', lead.phone],
                  ['Alternate Phone', lead.alternate_phone || '—'],
                  ['State', lead.state || '—'],
                  ['Pincode', lead.pincode || '—'],
                ].map(([k,v]) => (
                  <div key={String(k)}>
                    <div className="font-heading font-bold" style={{ fontSize: '0.68rem', color: '#888', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{k}</div>
                    <div className="font-medium mt-0.5" style={{ fontSize: '0.85rem' }}>{String(v)}</div>
                  </div>
                ))}
              </div>
              {lead.requirement && (
                <div className="mt-4 p-3" style={{ background: '#fffbee', border: '2px solid #ffe17c' }}>
                  <div className="font-heading font-bold mb-1" style={{ fontSize: '0.72rem', color: '#888', textTransform: 'uppercase' }}>Requirement</div>
                  <p style={{ fontSize: '0.85rem', lineHeight: 1.6 }}>{lead.requirement}</p>
                </div>
              )}
              {lead.tags?.length > 0 && (
                <div className="mt-3 flex gap-1 flex-wrap">
                  {lead.tags.map(t => <span key={t} className="tag">{t}</span>)}
                </div>
              )}
              {/* Upcoming follow-ups */}
              {(followupsData?.results?.filter(f => !f.is_completed) ?? []).length > 0 && (
                <div className="mt-4">
                  <div className="font-heading font-black mb-2" style={{ fontSize: '0.85rem' }}>Upcoming Follow-ups</div>
                  {followupsData!.results.filter(f => !f.is_completed).slice(0,3).map(fu => (
                    <div key={fu.id} className="flex items-center justify-between p-2 mb-1"
                         style={{ background: fu.is_overdue ? '#fee2e2' : '#f0fdf4', border: '2px solid #000' }}>
                      <span style={{ fontSize: '0.8rem' }}>{fu.followup_type_display} — {fmtDateTime(fu.scheduled_at)}</span>
                      <button onClick={() => completeFuMut.mutate(fu.id)}
                              className="btn-brutal px-2 py-0.5 font-heading font-bold" style={{ fontSize: '0.65rem', background: '#22c55e', color: '#fff', boxShadow: '2px 2px 0 #000' }}>
                        ✓ Done
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Notes */}
          {tab === 'Notes' && (
            <div className="p-5">
              <div className="flex gap-2 mb-4">
                <textarea value={noteText} onChange={e => setNoteText(e.target.value)}
                          className="input-brutal flex-1" rows={2} placeholder="Add a note…" />
                <button onClick={() => addNoteMut.mutate()} disabled={!noteText.trim() || addNoteMut.isPending}
                        className="btn-brutal btn-primary px-4 font-heading font-black" style={{ fontSize: '0.85rem', alignSelf: 'stretch' }}>
                  Add
                </button>
              </div>
              {(notesData?.results ?? []).length === 0 ? <EmptyState icon="✎" title="No notes yet" message="Add the first note." /> :
                (notesData!.results.map(note => (
                  <div key={note.id} className="p-3 mb-2" style={{ border: '2px solid #e5e5e5', background: note.is_pinned ? '#fffbee' : '#fff' }}>
                    <div className="flex justify-between mb-1">
                      <span className="font-heading font-bold" style={{ fontSize: '0.75rem' }}>{note.agent_name ?? 'System'}{note.is_pinned && ' 📌'}</span>
                      <span style={{ fontSize: '0.7rem', color: '#888' }}>{fmtRelative(note.created_at)}</span>
                    </div>
                    <p style={{ fontSize: '0.85rem', lineHeight: 1.6 }}>{note.content}</p>
                  </div>
                )))}
            </div>
          )}

          {/* Follow-ups */}
          {tab === 'Follow-ups' && (
            <div className="p-5">
              <button onClick={() => setShowFollowupModal(true)}
                      className="btn-brutal btn-primary px-3 py-2 font-heading font-black mb-4" style={{ fontSize: '0.82rem' }}>
                + Schedule Follow-up
              </button>
              {(followupsData?.results ?? []).length === 0 ? <EmptyState icon="⏰" title="No follow-ups" /> :
                followupsData!.results.map(fu => (
                  <div key={fu.id} className="flex items-center justify-between p-3 mb-2"
                       style={{ border: '2px solid #000', background: fu.is_completed ? '#f0fdf4' : fu.is_overdue ? '#fee2e2' : '#fff' }}>
                    <div>
                      <div className="font-heading font-bold" style={{ fontSize: '0.82rem' }}>{fu.followup_type_display} — {fmtDateTime(fu.scheduled_at)}</div>
                      {fu.notes && <p style={{ fontSize: '0.75rem', color: '#666', marginTop: '2px' }}>{fu.notes}</p>}
                      <span className="font-medium" style={{ fontSize: '0.7rem', color: fu.is_completed ? '#22c55e' : fu.is_overdue ? '#ef4444' : '#555' }}>
                        {fu.is_completed ? '✓ Completed' : fu.is_overdue ? '⚠ Overdue' : 'Pending'}
                      </span>
                    </div>
                    {!fu.is_completed && (
                      <button onClick={() => completeFuMut.mutate(fu.id)}
                              className="btn-brutal px-2 py-1 font-heading font-bold" style={{ fontSize: '0.68rem', background: '#22c55e', color: '#fff', boxShadow: '2px 2px 0 #000' }}>
                        ✓ Done
                      </button>
                    )}
                  </div>
                ))}
            </div>
          )}

          {/* Activity */}
          {tab === 'Activity' && (
            <div className="p-5">
              {(activitiesData as { results?: unknown[] } | undefined)?.results?.length === 0 ? <EmptyState icon="○" title="No activity yet" /> :
                ((activitiesData as { results?: Array<{id:number;activity_type:string;description:string;performed_by_name:string|null;timestamp:string}> } | undefined)?.results ?? []).map(a => (
                  <div key={a.id} className="flex gap-3 mb-3 pb-3" style={{ borderBottom: '1px solid #eee' }}>
                    <div style={{ width: '28px', height: '28px', background: '#ffe17c', border: '2px solid #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.8rem', flexShrink: 0 }}>
                      {a.activity_type === 'call' ? '☎' : a.activity_type === 'whatsapp' ? '✉' : a.activity_type === 'status_change' ? '→' : '○'}
                    </div>
                    <div>
                      <p style={{ fontSize: '0.83rem', lineHeight: 1.5 }}>{a.description}</p>
                      <div style={{ fontSize: '0.7rem', color: '#888', marginTop: '2px' }}>
                        {a.performed_by_name ?? 'System'} · {fmtRelative(a.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          )}

          {/* Calls */}
          {tab === 'Calls' && (
            <div className="p-5">
              <button onClick={() => setShowCallModal(true)}
                      className="btn-brutal btn-primary px-3 py-2 font-heading font-black mb-4" style={{ fontSize: '0.82rem' }}>
                + Log Manual Call
              </button>
              {(callsData?.results ?? []).length === 0 ? <EmptyState icon="☎" title="No calls logged" /> :
                callsData!.results.map(c => (
                  <div key={c.id} className="flex items-center justify-between p-3 mb-2" style={{ border: '2px solid #000', background: '#fff' }}>
                    <div>
                      <div className="flex items-center gap-2">
                        <span style={{ fontSize: '1rem' }}>{c.direction === 'outbound' ? '↗' : '↙'}</span>
                        <span className="font-heading font-bold" style={{ fontSize: '0.82rem' }}>{c.duration_display}</span>
                        {c.is_connected ? <span className="badge status-active">Connected</span> : <span className="badge status-inactive">No Answer</span>}
                        {c.disposition_name && <span className="tag">{c.disposition_name}</span>}
                      </div>
                      {c.notes && <p style={{ fontSize: '0.75rem', color: '#666', marginTop: '2px' }}>{c.notes}</p>}
                      <div style={{ fontSize: '0.7rem', color: '#888', marginTop: '2px' }}>{c.agent_name} · {fmtRelative(c.started_at)}</div>
                    </div>
                    {c.recording?.playback_url && (
                      <audio controls src={c.recording.playback_url} style={{ height: '32px' }} />
                    )}
                  </div>
                ))}
            </div>
          )}

          {/* WhatsApp */}
          {tab === 'WhatsApp' && (
            <div className="p-5">
              <div style={{ maxHeight: '320px', overflowY: 'auto', marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {(waMessages as { results?: Array<{id:string;direction:string;content:string;status:string;sent_at:string|null;sent_by_name:string|null}> } | undefined)?.results?.map(msg => (
                  <div key={msg.id} style={{
                    maxWidth: '80%', padding: '10px 14px', border: '2px solid #000',
                    background: msg.direction === 'outbound' ? '#fffbee' : '#f0f9ff',
                    alignSelf: msg.direction === 'outbound' ? 'flex-end' : 'flex-start',
                  }}>
                    <p style={{ fontSize: '0.85rem' }}>{msg.content}</p>
                    <div style={{ fontSize: '0.65rem', color: '#888', marginTop: '4px', textAlign: msg.direction === 'outbound' ? 'right' : 'left' }}>
                      {msg.sent_by_name ?? 'System'} · {fmtRelative(msg.sent_at)} · {msg.status}
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-2">
                <textarea value={waMessage} onChange={e => setWaMessage(e.target.value)}
                          className="input-brutal flex-1" rows={2} placeholder="Type WhatsApp message…" />
                <button onClick={() => sendWaMut.mutate()} disabled={!waMessage.trim() || sendWaMut.isPending}
                        className="btn-brutal btn-primary px-4 font-heading font-black" style={{ fontSize: '0.85rem', alignSelf: 'stretch' }}>
                  Send ✉
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {showEdit && <LeadFormModal lead={lead} onClose={() => setShowEdit(false)} onSuccess={() => { qc.invalidateQueries({ queryKey: ['lead', id] }); setShowEdit(false); showToast('success', 'Lead updated', ''); }} />}

      {showFollowupModal && (
        <Modal title="Schedule Follow-up" onClose={() => setShowFollowupModal(false)}>
          <div className="flex flex-col gap-3">
            <Select label="Type" value={followupForm.followup_type} onChange={e => setFollowupForm(p => ({ ...p, followup_type: e.target.value }))}>
              {['call','email','whatsapp','visit','meeting'].map(t => <option key={t} value={t}>{t.charAt(0).toUpperCase()+t.slice(1)}</option>)}
            </Select>
            <Input label="Scheduled At *" type="datetime-local" value={followupForm.scheduled_at} onChange={e => setFollowupForm(p => ({ ...p, scheduled_at: e.target.value }))} />
            <Textarea label="Notes" value={followupForm.notes} onChange={e => setFollowupForm(p => ({ ...p, notes: e.target.value }))} />
          </div>
          <div className="flex gap-3 mt-4"><button onClick={() => setShowFollowupModal(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
          <button onClick={() => addFollowupMut.mutate()} className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>Schedule →</button></div>
        </Modal>
      )}

      {showCallModal && (
        <Modal title="Log Manual Call" onClose={() => setShowCallModal(false)}>
          <div className="flex flex-col gap-3">
            <Select label="Direction" value={callForm.direction} onChange={e => setCallForm(p => ({ ...p, direction: e.target.value }))}>
              <option value="outbound">Outbound (I called)</option>
              <option value="inbound">Inbound (They called)</option>
            </Select>
            <Input label="Duration (seconds)" type="number" value={callForm.duration_seconds} onChange={e => setCallForm(p => ({ ...p, duration_seconds: e.target.value }))} placeholder="e.g. 120" />
            <Select label="Disposition" value={callForm.disposition} onChange={e => setCallForm(p => ({ ...p, disposition: e.target.value }))}>
              <option value="">No disposition</option>
              {dispositions?.map(d => <option key={d.id} value={String(d.id)}>{d.name}</option>)}
            </Select>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={callForm.is_connected} onChange={e => setCallForm(p => ({ ...p, is_connected: e.target.checked }))} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Call was answered</span>
            </label>
            <Textarea label="Notes" value={callForm.notes} onChange={e => setCallForm(p => ({ ...p, notes: e.target.value }))} />
          </div>
          <div className="flex gap-3 mt-4"><button onClick={() => setShowCallModal(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
          <button onClick={() => logCallMut.mutate()} className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>Log Call →</button></div>
        </Modal>
      )}
    </div>
  );
}
