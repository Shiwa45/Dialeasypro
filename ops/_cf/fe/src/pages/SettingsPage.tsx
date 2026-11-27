import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsApi, callsApi, authApi } from '../api';
import { SectionHeader, Modal, Input, Select, Spinner, useToast, EmptyState, ConfirmDialog } from '../components/ui';
import { getErrorMessage } from '../utils/errors';
import { LEAD_STATUSES } from '../utils/fmt';
import { useFeatures } from '../hooks/useFeatures';
import { AREAS, LockMark, UpgradeScreen } from '../components/UpgradeGate';
import { useAuthStore } from '../store/authStore';
import WhatsAppSettings from './WhatsAppSettings';
import BillingPanel from './BillingPanel';
import TeamsPanel from './TeamsPanel';
import CompanyProfilePanel from './CompanyProfilePanel';
import CustomFieldsPanel from './CustomFieldsPanel';
import type { CallDisposition, DispositionCategory } from '../types';
import { isAdmin as isAdminRole } from '../utils/roles';

// A new outcome is active and neutral until the admin says otherwise.
type DispForm = {
  id?: number; name: string; is_positive: boolean; is_active: boolean; sort_order: string;
  auto_followup_hours: string; lead_status: string; category: DispositionCategory; sets_dnd: boolean;
  is_system?: boolean;
};
const newDisposition = (category: DispositionCategory): DispForm => ({
  name: '', is_positive: false, is_active: true, sort_order: '0', auto_followup_hours: '',
  lead_status: '', category, sets_dnd: false,
});
// Outcomes come in two groups. After a call the agent sees only the group
// matching whether it was answered — there is no "dialer decides" any more.
const DISPOSITION_GROUPS: Array<{ category: DispositionCategory; title: string; sub: string }> = [
  { category: 'connected', title: 'Answered calls', sub: 'Offered when the call was answered.' },
  { category: 'not_connected', title: 'Unanswered calls', sub: 'Offered when nobody answered.' },
];

type SettingsTab = 'custom-fields' | 'dispositions' | 'teams' | 'whatsapp' | 'company' | 'access' | 'call-tracking' | 'unassign' | 'danger' | 'billing';

export default function Settings() {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const { isLocked } = useFeatures();
  const { agent } = useAuthStore();
  // Shown on every plan; without WhatsApp in the plan the tab is locked and
  // explains what an upgrade adds.
  const whatsAppLocked = isLocked(AREAS.whatsappSettings.gate);
  const agentWebLocked = isLocked(AREAS.agentWeb.gate);
  // ?tab=billing opens a tab directly — the upgrade screen links there.
  // Admin-only tabs fall back to the first tab for everyone else.
  const [searchParams] = useSearchParams();
  const tabFromUrl = (): SettingsTab | null => {
    const asked = searchParams.get('tab') as SettingsTab | null;
    const adminOnly: SettingsTab[] = ['company', 'access', 'call-tracking', 'unassign', 'danger', 'billing'];
    const known: SettingsTab[] = ['custom-fields', 'dispositions', 'teams', 'whatsapp', ...adminOnly];
    if (!asked || !known.includes(asked)) return null;
    return adminOnly.includes(asked) && !isAdminRole(agent) ? null : asked;
  };
  const [tab, setTab] = useState<SettingsTab>(() => tabFromUrl() ?? 'custom-fields');
  // Following a ?tab= link while already on Settings (the upgrade dialog's
  // "See plan & billing") must switch the tab too.
  useEffect(() => {
    const t = tabFromUrl();
    if (t) setTab(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const [dispModal, setDispModal] = useState<DispForm | null>(null);
  const [dispToRemove, setDispToRemove] = useState<CallDisposition | null>(null);
  const [unassignAgentId, setUnassignAgentId] = useState<string>('');
  // Flushing every lead lived on the Leads screen, one button away from
  // Export, which is not where a permanent delete of the whole workspace
  // belongs.
  const [flushConfirm, setFlushConfirm] = useState('');
  const [showUnassignConfirm, setShowUnassignConfirm] = useState(false);

  const isAdmin = isAdminRole(agent);
  const canEditDispositions = isAdmin;
  const dispQ = useQuery({
    queryKey: ['dispositions', canEditDispositions],
    queryFn: () => callsApi.dispositions(canEditDispositions ? { include_inactive: true } : undefined).then(r => r.data),
    enabled: tab === 'dispositions',
  });
  const agentsQ = useQuery({
    queryKey: ['agents-for-unassign'],
    // is_active: 'all' — a deactivated agent can still have leads assigned
    // to them and needs to show up here to be unassigned from.
    queryFn: () => authApi.listAgents({ page_size: 200, is_active: 'all' }).then(r => r.data),
    enabled: tab === 'unassign',
  });

  const flushMut = useMutation({
    mutationFn: () => leadsApi.flush(flushConfirm).then(r => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      qc.invalidateQueries({ queryKey: ['lead-batches'] });
      showToast('success', 'Leads flushed', `${data.deleted} lead(s) permanently deleted.`);
      setFlushConfirm('');
    },
    onError: (e: unknown) =>
      showToast('error', 'Flush failed', getErrorMessage(e, 'Please try again.')),
  });

  const unassignMut = useMutation({
    mutationFn: () => leadsApi.unassignByAgent(Number(unassignAgentId)),
    onSuccess: (r) => {
      showToast('success', 'Leads unassigned', `${r.data.unassigned} lead(s) unassigned from ${r.data.agent}. Nothing was deleted.`);
      setShowUnassignConfirm(false);
      setUnassignAgentId('');
      qc.invalidateQueries({ queryKey: ['leads'] });
    },
    onError: (e: unknown) => {
      showToast('error', 'Failed', getErrorMessage(e, 'Could not unassign leads.'));
      setShowUnassignConfirm(false);
    },
  });

  const selectedAgent = (agentsQ.data?.results ?? []).find(a => String(a.id) === unassignAgentId);

  // The dialer, the call log and the mobile app all read this list, so every
  // write invalidates it wherever it is cached.
  const refreshDispositions = () => qc.invalidateQueries({ queryKey: ['dispositions'] });

  const saveDispMut = useMutation({
    mutationFn: () => {
      const f = dispModal!;
      const payload = {
        name: f.name.trim(),
        is_positive: f.is_positive,
        is_active: f.is_active,
        sort_order: Number(f.sort_order) || 0,
        // Blank means "no automatic follow-up", which the API stores as null.
        // Blank means "no automatic follow-up" (by default only Busy,
        // Call back later and Voicemail book one).
        auto_followup_hours: f.auto_followup_hours === '' ? null : Number(f.auto_followup_hours),
        lead_status: f.lead_status,
        sets_dnd: f.sets_dnd,
        // A built-in outcome keeps its group.
        ...(f.is_system ? {} : { category: f.category }),
      };
      return f.id ? callsApi.updateDisposition(f.id, payload) : callsApi.createDisposition(payload);
    },
    onSuccess: (_r, _v, _c) => {
      const edited = !!dispModal?.id;
      refreshDispositions();
      setDispModal(null);
      showToast('success', edited ? 'Outcome updated' : 'Outcome added', '');
    },
    onError: (e: unknown) => showToast('error', 'Could not save', getErrorMessage(e, 'Failed to save the call outcome.')),
  });

  const removeDispMut = useMutation({
    mutationFn: (d: CallDisposition) => callsApi.deleteDisposition(d.id),
    onSuccess: (r) => {
      refreshDispositions();
      setDispToRemove(null);
      // Deleting an outcome that calls already carry would blank it on every
      // one of them, so the server switches it off instead and says so.
      if (r.status === 200 && r.data?.deactivated) showToast('success', 'Outcome switched off', r.data.detail ?? '');
      else showToast('success', 'Outcome deleted', '');
    },
    onError: (e: unknown) => {
      setDispToRemove(null);
      showToast('error', 'Could not remove', getErrorMessage(e, 'Failed to remove the call outcome.'));
    },
  });

  const TABS = [
    { k: 'custom-fields', l: '☰ Custom Fields' },
    { k: 'dispositions', l: '☎ Call Dispositions' },
    { k: 'teams', l: '◉ Teams' },
    { k: 'whatsapp', l: '💬 WhatsApp', locked: whatsAppLocked },
    ...(isAdmin ? [{ k: 'company', l: '▣ Company Profile' }] as const : []),
    ...(isAdmin ? [{ k: 'access', l: '🔑 Web Access', locked: agentWebLocked }] as const : []),
    ...(isAdmin ? [{ k: 'call-tracking', l: '📞 Call Tracking' }] as const : []),
    ...(isAdmin ? [{ k: 'unassign', l: '⇄ Unassign Leads' }] as const : []),
    ...(isAdmin ? [{ k: 'danger', l: '⚠ Danger Zone' }] as const : []),
    ...(isAdmin ? [{ k: 'billing', l: '₹ Billing' }] as const : []),
  ] as const;

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: 'var(--paper)', minHeight: '100%' }}>
      <SectionHeader title="Settings" sub="Configure your CRM workspace" />

      <div style={{ display: 'flex', borderBottom: '1px solid var(--line)', overflowX: 'auto' }}>
        {TABS.map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} className="font-heading font-bold px-4 py-2.5"
                  style={{ background: tab === t.k ? 'var(--brass-50)' : 'var(--surface)', border: 'none', borderRight: '1px solid var(--line)', cursor: 'pointer', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
            {t.l}
            {'locked' in t && t.locked && <> <LockMark title="Upgrade to unlock" /></>}
          </button>
        ))}
      </div>

      {/* Custom Fields */}
      {tab === 'custom-fields' && <CustomFieldsPanel canEdit={isAdmin} />}

      {/* Call Dispositions */}
      {tab === 'dispositions' && (
        <div className="flex flex-col gap-4">
          {dispQ.isLoading ? <Spinner /> : DISPOSITION_GROUPS.map(group => {
            const rows = (dispQ.data ?? []).filter(d => d.category === group.category);
            return (
              <div key={group.category} className="card" style={{ overflowX: 'auto' }}>
                <div className="px-4 py-3 border-b-2 border-black flex items-center justify-between gap-3 flex-wrap"
                     style={{ background: 'var(--surface-2)' }}>
                  <div>
                    <span className="font-heading font-black" style={{ color: 'var(--text)', fontSize: '0.95rem' }}>▸ {group.title}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginLeft: 8 }}>{group.sub}</span>
                  </div>
                  {canEditDispositions && (
                    <button onClick={() => setDispModal(newDisposition(group.category))}
                            className="btn-brutal btn-primary px-3 py-1.5 font-heading font-black" style={{ fontSize: '0.78rem' }}>
                      + Add outcome
                    </button>
                  )}
                </div>
                {rows.length === 0 ? (
                  <EmptyState icon="☎" title="No outcomes in this group"
                              message="Agents need at least one outcome here to save a call." />
                ) : (
                  <table className="table-brutal">
                    <thead><tr>{['Outcome', 'Sets lead to', 'Auto follow-up', 'Type', 'Order', 'Status', ...(canEditDispositions ? [''] : [])].map((h, i) => <th key={h || `actions-${i}`}>{h}</th>)}</tr></thead>
                    <tbody>
                      {rows.map(d => (
                        <tr key={d.id} style={d.is_active ? undefined : { opacity: 0.6 }}>
                          <td className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>
                            {d.name}
                            {d.is_system && <span className="tag" style={{ marginLeft: 6, fontSize: '0.62rem' }}>Built-in</span>}
                            {d.sets_dnd && <span className="tag" style={{ marginLeft: 6, fontSize: '0.62rem' }}>Marks DND</span>}
                          </td>
                          <td style={{ fontSize: '0.8rem' }}>
                            {LEAD_STATUSES.find(s => s.value === d.lead_status)?.label
                              ?? <span style={{ color: 'var(--text-3)' }}>{group.category === 'connected' ? 'Contacted (at least)' : 'Attempted (at least)'}</span>}
                          </td>
                          <td style={{ fontSize: '0.8rem' }}>
                            {d.auto_followup_hours
                              ? `In ${d.auto_followup_hours} hours`
                              : <span style={{ color: 'var(--text-3)' }}>None</span>}
                          </td>
                          <td>{d.is_positive ? <span className="badge status-active">Positive</span> : <span className="badge status-inactive">Neutral / negative</span>}</td>
                          <td style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>{d.sort_order}</td>
                          <td>{d.is_active ? <span className="badge status-active">Active</span> : <span className="badge status-inactive">Switched off</span>}</td>
                          {canEditDispositions && (
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <button onClick={() => setDispModal({
                                        id: d.id, name: d.name, is_positive: d.is_positive, is_active: d.is_active,
                                        sort_order: String(d.sort_order ?? 0),
                                        auto_followup_hours: d.auto_followup_hours == null ? '' : String(d.auto_followup_hours),
                                        lead_status: d.lead_status ?? '', category: d.category,
                                        sets_dnd: !!d.sets_dnd, is_system: !!d.is_system,
                                      })}
                                      className="font-heading font-bold px-2 py-1"
                                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--brass)' }}>
                                Edit
                              </button>
                              {!d.is_system && (
                                <button onClick={() => setDispToRemove(d)}
                                        className="font-heading font-bold px-2 py-1"
                                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--hot)' }}>
                                  Remove
                                </button>
                              )}
                            </td>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
          <p style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>
            A call outcome only moves a lead forward through the pipeline (New → Attempted → Contacted →
            Interested / Follow-up → Negotiation → Converted). Outcomes that close a lead — Not interested,
            Lost, Invalid — apply at any stage. Converted and Duplicate leads are never changed by a call.
            Built-in outcomes can be renamed or switched off, not deleted.
          </p>
        </div>
      )}

      {/* Teams */}
      {tab === 'teams' && <TeamsPanel canEdit={isAdmin} />}

      {/* WhatsApp connection */}
      {tab === 'whatsapp' && (whatsAppLocked
        ? <UpgradeScreen area={AREAS.whatsappSettings} compact />
        : <WhatsAppSettings />)}

      {/* Unassign Leads — admin only */}
      {tab === 'unassign' && isAdmin && (
        <div className="card p-5" style={{ maxWidth: '520px' }}>
          <div className="font-heading font-black mb-2" style={{ fontSize: '1rem' }}>Unassign Leads by Agent</div>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-2)', lineHeight: 1.6, marginBottom: '18px' }}>
            Pick an agent to remove them as the assignee from every lead currently assigned to
            them. This only clears the assignment — the leads themselves, their notes, and their
            history are kept exactly as they are and are <strong>never deleted</strong>.
          </p>
          {agentsQ.isLoading ? <Spinner /> : (
            <div className="flex flex-col gap-3">
              <Select
                label="Agent"
                value={unassignAgentId}
                onChange={e => setUnassignAgentId(e.target.value)}
              >
                <option value="">Select an agent…</option>
                {(agentsQ.data?.results ?? []).map(a => (
                  <option key={a.id} value={a.id}>
                    {a.name} ({a.email}){!a.is_active ? ' — deactivated' : ''}
                  </option>
                ))}
              </Select>
              <button
                onClick={() => setShowUnassignConfirm(true)}
                disabled={!unassignAgentId}
                className="btn-brutal btn-primary py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: 'var(--shadow)' }}
              >
                Unassign all leads from this agent →
              </button>
            </div>
          )}
        </div>
      )}

      {/* Billing */}
      {tab === 'danger' && (
        <div className="card p-5" style={{ maxWidth: '560px', borderColor: 'var(--hot)' }}>
          <div className="font-heading font-black mb-2" style={{ fontSize: '1rem', color: 'var(--hot)' }}>
            Flush all leads
          </div>
          <div style={{ background: 'var(--hot-50)', border: '1px solid var(--hot)', padding: '12px',
                        fontSize: '0.82rem', lineHeight: 1.6, marginBottom: 14 }}>
            This <strong>permanently deletes every lead</strong> in this workspace, along with
            their notes, follow-ups and activity history. Agents, settings and templates are
            kept. <strong>It cannot be undone.</strong>
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-2)', marginBottom: 6 }}>
            Type <strong>FLUSH ALL</strong> to confirm:
          </div>
          <Input label="" value={flushConfirm} placeholder="FLUSH ALL"
                 onChange={e => setFlushConfirm(e.target.value)} />
          <button onClick={() => flushMut.mutate()}
                  disabled={flushMut.isPending || flushConfirm.trim().toUpperCase() !== 'FLUSH ALL'}
                  className="btn-brutal btn-danger px-4 py-2.5 font-heading font-black mt-3"
                  style={{ fontSize: '0.85rem' }}>
            {flushMut.isPending ? '◌ Deleting…' : 'Permanently delete all leads'}
          </button>
        </div>
      )}

      {tab === 'company' && isAdmin && <CompanyProfilePanel />}
      {tab === 'access' && isAdmin && <WebAccessPanel />}
      {tab === 'call-tracking' && isAdmin && <CallTrackingPanel />}
      {tab === 'billing' && <BillingPanel />}

      {/* Call outcome modal */}
      {dispModal && (
        <Modal title={dispModal.id ? 'Edit Call Outcome' : 'New Call Outcome'} onClose={() => setDispModal(null)}>
          <div className="flex flex-col gap-3">
            <Input label="Outcome Name *" value={dispModal.name} autoFocus
                   onChange={e => setDispModal(p => p && ({ ...p, name: e.target.value }))}
                   placeholder="e.g. Site Visit Booked, Not Reachable" />
            <Select label="Set Lead Status To" value={dispModal.lead_status}
                    onChange={e => setDispModal(p => p && ({ ...p, lead_status: e.target.value }))}
                    hint="Moves the lead forward to this stage (never backwards). Not interested, Lost and Invalid close the lead at any stage. Converted and duplicate leads are never changed.">
              <option value="">Only the minimum (Contacted if answered, Attempted if not)</option>
              {LEAD_STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </Select>
            <Select label="Group" value={dispModal.category} disabled={dispModal.is_system}
                    onChange={e => setDispModal(p => p && ({ ...p, category: e.target.value as DispositionCategory }))}
                    hint={dispModal.is_system
                      ? 'A built-in outcome stays in its group.'
                      : 'Agents see this outcome only for calls of this kind. It never changes whether a call counts as answered.'}>
              <option value="connected">Answered calls</option>
              <option value="not_connected">Unanswered calls</option>
            </Select>
            <Input label="Automatic follow-up after (hours)" type="number" min={0} value={dispModal.auto_followup_hours}
                   onChange={e => setDispModal(p => p && ({ ...p, auto_followup_hours: e.target.value }))}
                   placeholder="Leave blank for none"
                   hint="Books a call-back this many hours after a call with this outcome. By default only Busy, Call back later and Voicemail do; leave blank for none." />
            <Input label="Sort Order" type="number" min={0} value={dispModal.sort_order}
                   onChange={e => setDispModal(p => p && ({ ...p, sort_order: e.target.value }))}
                   hint="Where it sits in the list an agent picks from. Lower shows first." />
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={dispModal.is_positive}
                     onChange={e => setDispModal(p => p && ({ ...p, is_positive: e.target.checked }))}
                     style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Positive outcome (a good result — counts towards the conversion reports)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={dispModal.sets_dnd}
                     onChange={e => setDispModal(p => p && ({ ...p, sets_dnd: e.target.checked }))}
                     style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Mark the lead Do Not Disturb (they asked not to be called)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={dispModal.is_active}
                     onChange={e => setDispModal(p => p && ({ ...p, is_active: e.target.checked }))}
                     style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Active (offered to agents after a call)</span>
            </label>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setDispModal(null)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => saveDispMut.mutate()} disabled={saveDispMut.isPending || !dispModal.name.trim()}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: 'var(--shadow)' }}>
              {saveDispMut.isPending ? '◌ Saving…' : dispModal.id ? 'Save Changes →' : 'Add Outcome →'}
            </button>
          </div>
        </Modal>
      )}

      {dispToRemove && (
        <ConfirmDialog
          title={`Remove "${dispToRemove.name}"?`}
          message="Agents will stop being offered this outcome. If calls have already been logged with it, it is switched off rather than deleted, so those calls keep their outcome in your reports."
          confirmLabel={removeDispMut.isPending ? 'Removing…' : 'Remove'}
          danger
          onConfirm={() => removeDispMut.mutate(dispToRemove)}
          onCancel={() => setDispToRemove(null)}
        />
      )}


      {/* Unassign confirm */}
      {showUnassignConfirm && selectedAgent && (
        <ConfirmDialog
          title="Unassign leads?"
          message={`This removes ${selectedAgent.name} as the assigned agent from every lead currently assigned to them. The leads are not deleted — they stay in the system, unassigned and ready to be reassigned.`}
          confirmLabel={unassignMut.isPending ? 'Unassigning…' : 'Unassign'}
          onConfirm={() => unassignMut.mutate()}
          onCancel={() => setShowUnassignConfirm(false)}
        />
      )}
    </div>
  );
}


/* ---- Phone call tracking ---------------------------------------
   With the company switch on, the mobile app of every agent whose own switch
   is on asks for the call-log and storage permissions, then saves all their
   incoming and outgoing calls (missed ones included) and uploads the
   recordings. Agents are on by default; switch off whoever should not be
   tracked (personal phones, for example). */
function CallTrackingPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ['call-tracking'],
    queryFn: () => callsApi.tracking().then(r => r.data),
  });
  const save = useMutation({
    mutationFn: (body: { enabled?: boolean; agents?: Record<string, boolean> }) => callsApi.setTracking(body),
    onSuccess: (r, body) => {
      qc.setQueryData(['call-tracking'], r.data);
      if (body.enabled !== undefined) {
        showToast('success', body.enabled ? 'Call tracking turned on' : 'Call tracking turned off',
          body.enabled
            ? 'Agents are asked for the permissions the next time they open the mobile app.'
            : 'The mobile app stops saving phone calls. Calls already saved are kept.');
      }
    },
    onError: (e: unknown) => showToast('error', 'Could not save', getErrorMessage(e)),
  });

  if (isLoading || !data) return <Spinner />;
  const on = data.enabled;
  const tracked = data.agents.filter(a => a.call_tracking_enabled).length;

  return (
    <div className="card p-5" style={{ maxWidth: 720 }}>
      <div className="font-heading font-black" style={{ fontSize: '1rem', marginBottom: 6 }}>
        Phone call tracking
      </div>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 14 }}>
        When on, the DialSathi mobile app saves <b>every incoming and outgoing call</b> on the
        agent's phone — including calls not made from the app and missed calls — and uploads
        the call recording. Calls from numbers that aren't leads are saved without a lead.
        Each agent has to allow the call-log and storage permissions on their phone.
      </p>
      <label className="flex items-center gap-3" style={{ cursor: 'pointer', marginBottom: 16 }}>
        <input type="checkbox" checked={on} disabled={save.isPending}
               onChange={e => save.mutate({ enabled: e.target.checked })}
               style={{ width: 18, height: 18 }} />
        <span className="font-heading font-bold" style={{ fontSize: '0.9rem' }}>
          Track phone calls for my company
        </span>
      </label>

      <div className="font-heading font-bold" style={{ fontSize: '0.85rem', marginBottom: 4 }}>
        Agents {on ? `(${tracked} of ${data.agents.length} tracked)` : '(tracking is off)'}
      </div>
      <p style={{ fontSize: '0.76rem', color: 'var(--text-3)', marginBottom: 8 }}>
        Untick anyone who should not be tracked, for example an agent using a personal phone.
      </p>
      <div style={{ border: '1px solid var(--line)', maxHeight: 360, overflowY: 'auto', opacity: on ? 1 : 0.55 }}>
        {data.agents.map(a => (
          <label key={a.id} className="flex items-center gap-3"
                 style={{ padding: '8px 12px', borderBottom: '1px solid var(--line)', cursor: 'pointer' }}>
            <input type="checkbox" checked={a.call_tracking_enabled} disabled={save.isPending}
                   onChange={e => save.mutate({ agents: { [String(a.id)]: e.target.checked } })}
                   style={{ width: 16, height: 16 }} />
            <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>{a.name}</span>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-3)', textTransform: 'capitalize' }}>
              {a.role.replace('_', ' ')}
            </span>
          </label>
        ))}
        {data.agents.length === 0 && (
          <div style={{ padding: 12, fontSize: '0.8rem', color: 'var(--text-3)' }}>No active agents.</div>
        )}
      </div>
      <p style={{ fontSize: '0.76rem', color: 'var(--text-3)', lineHeight: 1.6, marginTop: 14 }}>
        Recordings come from the phone's own call recorder, so it must be switched on in the
        phone's dialer. Phones that use the Google Phone app keep recordings private to that
        app; those calls are saved without a recording.
      </p>
    </div>
  );
}


/* ---- Web access ----------------------------------------------
   Whether agents and read-only users may sign in on the web. They get a
   deliberately narrow workspace there (their own dashboard, leads and calls);
   some companies still want the floor on the mobile app only. */
function WebAccessPanel() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ['agent-web-access'],
    queryFn: () => authApi.webAccess().then(r => r.data),
  });
  const save = useMutation({
    mutationFn: (on: boolean) => authApi.setWebAccess(on),
    onSuccess: r => {
      qc.setQueryData(['agent-web-access'], r.data);
      showToast('success', r.data.agent_web_access ? 'Agents can sign in on the web' : 'Web sign-in turned off for agents',
        r.data.agent_web_access
          ? 'They see only their own dashboard, leads and call history.'
          : 'Agents already signed in on the web are signed out on their next page load. The mobile app is unaffected.');
    },
    onError: (e: unknown) => showToast('error', 'Could not save', getErrorMessage(e)),
  });

  if (isLoading || !data) return <Spinner />;
  // The server's answer, not the cached feature map: it is what PATCH checks.
  if (!data.available_in_plan) return <UpgradeScreen area={AREAS.agentWeb} compact />;
  const on = data.agent_web_access;

  return (
    <div className="card p-5" style={{ maxWidth: 620 }}>
      <div className="font-heading font-black" style={{ fontSize: '1rem', marginBottom: 6 }}>
        Agent web sign-in
      </div>
      <p style={{ fontSize: '0.84rem', color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 14 }}>
        When on, agents and read-only users can sign in to this web app. They see
        only <b>their own</b> performance dashboard, the leads assigned to them and
        their call history — no settings, reports, other agents or modules.
      </p>
      <label className="flex items-center gap-3" style={{ cursor: 'pointer' }}>
        <input type="checkbox" checked={on} disabled={save.isPending}
               onChange={e => save.mutate(e.target.checked)}
               style={{ width: 18, height: 18 }} />
        <span className="font-heading font-bold" style={{ fontSize: '0.9rem' }}>
          Allow agents to sign in on the web
        </span>
      </label>
      <p style={{ fontSize: '0.76rem', color: 'var(--text-3)', lineHeight: 1.6, marginTop: 14 }}>
        Turning this off affects the web app only. The DialSathi mobile app keeps
        working, and admins, managers, HR, accounts and recruiters are never
        affected — so you can't lock yourself out.
      </p>
    </div>
  );
}
