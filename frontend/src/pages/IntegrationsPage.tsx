import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { integrationsApi, leadsApi } from '../api';
import {
  SectionHeader, Modal, Select, Spinner, EmptyState,
  ConfirmDialog, useToast, Input,
} from '../components/ui';
import { fmtRelative } from '../utils/fmt';
import { LEAD_SOURCES } from '../utils/fmt';
import type { IntegrationConfig } from '../types';

const INTEGRATION_META: Record<string, { icon: string; color: string; description: string }> = {
  indiamart:     { icon: '🏭', color: '#ff6b00', description: "India's largest B2B marketplace. Buyer enquiries auto-captured." },
  meta_facebook: { icon: '📘', color: '#1877f2', description: 'Facebook & Instagram Lead Ads. Real-time lead form submissions.' },
  google_ads:    { icon: '🔍', color: '#4285f4', description: 'Google Ads Lead Form extensions. Capture Google leads directly.' },
  website:       { icon: '🌐', color: '#22c55e', description: 'Website contact forms via generic webhook integration.' },
  webhook:       { icon: '🔗', color: '#7c3aed', description: 'Generic webhook endpoint. Connect any external platform.' },
  referral:      { icon: '👥', color: '#f59e0b', description: 'Referral tracking for word-of-mouth leads.' },
};

export default function Integrations() {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);
  const [newSource, setNewSource] = useState('indiamart');
  const [logSource, setLogSource] = useState('');
  const [configTarget, setConfigTarget] = useState<IntegrationConfig | null>(null);
  const [creds, setCreds] = useState<{ verify_token: string; app_secret: string; access_token: string; api_key: string; page_id: string }>(
    { verify_token: '', app_secret: '', access_token: '', api_key: '', page_id: '' }
  );
  const [copied, setCopied] = useState('');
  const [mapRows, setMapRows] = useState<Array<{ metaField: string; target: string }>>([]);
  const [metaFieldOptions, setMetaFieldOptions] = useState<string[]>([]);

  // Tenant's custom fields, to offer as mapping targets.
  const { data: customFields } = useQuery({
    queryKey: ['custom-fields'],
    queryFn: () => leadsApi.listCustomFields().then(r => r.data),
  });

  const openConfigure = (cfg: IntegrationConfig) => {
    setConfigTarget(cfg);
    setCreds({
      verify_token: cfg.credentials_status?.verify_token || '',
      app_secret: '', access_token: '', api_key: '',
      page_id: (cfg.options?.page_id as string) || '',
    });
    // Seed mapping rows from saved options.field_mapping.
    const fm = (cfg.options?.field_mapping as Record<string, string>) || {};
    const rows = Object.entries(fm).map(([metaField, target]) => ({ metaField, target }));
    setMapRows(rows.length ? rows : [{ metaField: '', target: '' }]);
    setMetaFieldOptions([]);
  };

  const fetchMetaFields = async () => {
    try {
      const { data } = await integrationsApi.metaForms();
      const labels = new Set<string>();
      data.forms.forEach(f => f.fields.forEach(q => labels.add(q.label || q.key)));
      setMetaFieldOptions([...labels]);
      showToast('success', 'Fetched form fields', `${labels.size} fields from ${data.forms.length} form(s).`);
    } catch (e) {
      showToast('error', 'Could not fetch', (e as { response?: { data?: { message?: string } } })?.response?.data?.message ?? 'Save Page Access Token + Page ID first.');
    }
  };

  // Mapping targets: standard CRM fields + the tenant's custom fields.
  const STANDARD_TARGETS = [
    { value: 'name', label: 'Name' },
    { value: 'phone', label: 'Phone' },
    { value: 'alternate_phone', label: 'Alternate / WhatsApp phone' },
    { value: 'email', label: 'Email' },
    { value: 'city', label: 'City' },
    { value: 'state', label: 'State' },
    { value: 'pincode', label: 'Pincode' },
    { value: 'requirement', label: 'Requirement / Message' },
    { value: 'budget', label: 'Budget' },
    { value: 'campaign_name', label: 'Campaign Name' },
    { value: 'ad_name', label: 'Ad / Ad Set Name' },
    { value: 'ignore', label: '— Ignore —' },
  ];

  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(''), 1500);
  };

  const { data: configs, isLoading } = useQuery({
    queryKey: ['integrations'],
    queryFn: () => integrationsApi.listConfigs().then(r => r.data),
  });

  const { data: logs } = useQuery({
    queryKey: ['webhook-logs', logSource],
    queryFn: () => integrationsApi.listLogs(logSource || undefined).then(r => r.data),
    refetchInterval: 10000,
  });

  const createMut = useMutation({
    mutationFn: () => integrationsApi.createConfig({ source: newSource, is_active: true, options: {} } as unknown as import('../types').IntegrationConfig),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations'] });
      setShowCreate(false);
      showToast('success', 'Integration added', 'Configure the webhook URL in the source platform.');
    },
    onError: () => showToast('error', 'Error', 'Could not add integration.'),
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      integrationsApi.updateConfig(id, { is_active } as unknown as import('../types').IntegrationConfig),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations'] }),
  });

  const configureMut = useMutation({
    mutationFn: () => {
      // Only send credentials the user actually typed (blank = keep existing).
      const credPayload: Record<string, string> = {};
      if (creds.verify_token) credPayload.verify_token = creds.verify_token;
      if (creds.app_secret) credPayload.app_secret = creds.app_secret;
      if (creds.access_token) credPayload.access_token = creds.access_token;
      if (creds.api_key) credPayload.api_key = creds.api_key;
      if (creds.page_id) credPayload.page_id = creds.page_id;

      // Build field_mapping from the rows (skip empty).
      const field_mapping: Record<string, string> = {};
      mapRows.forEach(r => {
        if (r.metaField.trim() && r.target) field_mapping[r.metaField.trim()] = r.target;
      });
      const options = {
        ...(configTarget!.options || {}),
        field_mapping,
        ...(creds.page_id ? { page_id: creds.page_id } : {}),
      };

      return integrationsApi.updateConfig(
        configTarget!.id,
        { credentials: credPayload, options } as unknown as IntegrationConfig,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations'] });
      showToast('success', 'Credentials saved', 'Your integration is configured.');
      setConfigTarget(null);
    },
    onError: () => showToast('error', 'Error', 'Could not save credentials.'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => integrationsApi.deleteConfig(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrations'] });
      setConfirmDelete(null);
      showToast('info', 'Integration removed', '');
    },
  });

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Lead Source Integrations" sub="Connect platforms that automatically send leads to your CRM">
        <button onClick={() => setShowCreate(true)}
                className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          + Add Integration
        </button>
      </SectionHeader>

      {isLoading ? <Spinner /> : (
        <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))' }}>
          {(configs ?? []).map(cfg => {
            const meta = INTEGRATION_META[cfg.source];
            return (
              <div key={cfg.id} className="card p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div style={{ fontSize: '2rem', width: '48px', height: '48px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: meta?.color ?? '#e5e5e5', border: '2px solid #000', boxShadow: '3px 3px 0 #000' }}>
                      {meta?.icon ?? '○'}
                    </div>
                    <div>
                      <div className="font-heading font-black" style={{ fontSize: '0.95rem' }}>{cfg.source_display}</div>
                      <div style={{ fontSize: '0.7rem', color: cfg.status === 'error' ? '#ef4444' : cfg.is_active ? '#22c55e' : '#999', fontWeight: 700 }}>
                        ● {cfg.status === 'error' ? 'Error — check config' : cfg.is_active ? 'Active' : 'Inactive'}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => toggleMut.mutate({ id: cfg.id, is_active: !cfg.is_active })}
                    className="btn-brutal px-3 py-1 font-heading font-bold"
                    style={{ fontSize: '0.72rem', background: cfg.is_active ? '#dcfce7' : '#f3f4f6', boxShadow: '2px 2px 0 #000' }}
                  >
                    {cfg.is_active ? 'Active ✓' : 'Inactive'}
                  </button>
                </div>

                {meta?.description && (
                  <p style={{ fontSize: '0.78rem', color: '#666', marginBottom: '12px', lineHeight: 1.4 }}>{meta.description}</p>
                )}

                <div style={{ fontSize: '0.78rem', color: '#555', marginBottom: '10px' }}>
                  <div>Leads received: <strong>{cfg.total_leads_received}</strong></div>
                  <div>Last lead: {cfg.last_received_at ? fmtRelative(cfg.last_received_at) : 'Never'}</div>
                  {cfg.error_message && (
                    <div style={{ color: '#ef4444', marginTop: '4px' }}>⚠ {cfg.error_message}</div>
                  )}
                </div>

                <div style={{ background: '#f9f9f9', border: '2px solid #e5e5e5', padding: '8px 10px', marginBottom: '12px' }}>
                  <div className="flex items-center justify-between" style={{ marginBottom: '4px' }}>
                    <div style={{ fontSize: '0.65rem', color: '#888', fontFamily: 'Space Grotesk', fontWeight: 700, textTransform: 'uppercase' }}>
                      Webhook / Callback URL
                    </div>
                    <button onClick={() => copy(cfg.webhook_url, `url-${cfg.id}`)}
                            style={{ fontSize: '0.6rem', border: '1px solid #000', background: copied === `url-${cfg.id}` ? '#dcfce7' : '#fff', cursor: 'pointer', padding: '2px 6px', fontWeight: 700 }}>
                      {copied === `url-${cfg.id}` ? 'Copied ✓' : 'Copy'}
                    </button>
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.68rem', wordBreak: 'break-all', color: '#333' }}>
                    {cfg.webhook_url}
                  </div>
                </div>

                <div className="flex gap-2">
                  <button onClick={() => openConfigure(cfg)}
                          className="btn-brutal btn-primary px-3 py-1 font-heading font-bold flex-1" style={{ fontSize: '0.72rem', boxShadow: '2px 2px 0 #000' }}>
                    ⚙ Configure
                  </button>
                  <button onClick={() => setConfirmDelete(cfg.id)}
                          className="btn-brutal btn-danger px-3 py-1 font-heading font-bold" style={{ fontSize: '0.72rem' }}>
                    Remove
                  </button>
                </div>
              </div>
            );
          })}

          {(configs ?? []).length === 0 && (
            <div className="col-span-full">
              <EmptyState
                icon="⊕"
                title="No integrations configured"
                message="Connect IndiaMART, Meta Lead Ads, Google Ads, or any platform using our generic webhook."
                action={{ label: '+ Add Integration', onClick: () => setShowCreate(true) }}
              />
            </div>
          )}
        </div>
      )}

      {/* Webhook Logs */}
      <div className="card">
        <div className="px-4 py-3 border-b-2 border-black flex items-center justify-between"
             style={{ background: '#171e19' }}>
          <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.9rem' }}>
            ▸ Webhook Logs (live, auto-refreshes every 10s)
          </span>
          <select value={logSource} onChange={e => setLogSource(e.target.value)}
                  style={{ border: '2px solid #ffe17c', background: '#ffe17c', fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: '0.75rem', outline: 'none', cursor: 'pointer', padding: '4px 8px' }}>
            <option value="">All Sources</option>
            {LEAD_SOURCES.filter(s => !['manual', 'csv_import', 'other'].includes(s.value)).map(s => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
        </div>
        {(logs ?? []).length === 0 ? (
          <div style={{ padding: '28px', textAlign: 'center', color: '#999', fontSize: '0.82rem' }}>
            No webhook logs yet. Logs appear here when leads arrive via integrations.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="table-brutal">
              <thead>
                <tr>{['Source', 'Status', 'Leads Created', 'Leads Updated', 'Error', 'Received'].map(h => <th key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {(logs ?? []).slice(0, 50).map(log => (
                  <tr key={log.id}>
                    <td><span className="tag">{log.source_display}</span></td>
                    <td>
                      {log.processed
                        ? <span className="badge status-active">Processed</span>
                        : log.error
                          ? <span className="badge status-lost">Error</span>
                          : <span className="badge status-new">Pending</span>}
                    </td>
                    <td className="font-heading font-black" style={{ fontSize: '0.82rem', color: '#22c55e' }}>{log.leads_created}</td>
                    <td style={{ fontSize: '0.82rem' }}>{log.leads_updated}</td>
                    <td style={{ fontSize: '0.72rem', color: '#ef4444', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {log.error || '—'}
                    </td>
                    <td style={{ fontSize: '0.72rem', color: '#888' }}>{fmtRelative(log.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add integration modal */}
      {showCreate && (
        <Modal title="Add Lead Source Integration" onClose={() => setShowCreate(false)}>
          <Select label="Lead Source *" value={newSource} onChange={e => setNewSource(e.target.value)}>
            {LEAD_SOURCES
              .filter(s => !['manual', 'csv_import', 'other'].includes(s.value))
              .map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
          {INTEGRATION_META[newSource] && (
            <div style={{ marginTop: '10px', padding: '10px', background: '#fffbee', border: '2px solid #ffe17c', fontSize: '0.78rem' }}>
              {INTEGRATION_META[newSource].description}
            </div>
          )}
          <div style={{ marginTop: '10px', fontSize: '0.75rem', color: '#666' }}>
            After adding, click <strong>⚙ Configure</strong> on the integration card to enter your
            credentials (verify token, app secret, access token) and get the webhook URL to paste
            into the source platform.
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setShowCreate(false)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => createMut.mutate()}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
              Add Integration →
            </button>
          </div>
        </Modal>
      )}

      {confirmDelete !== null && (
        <ConfirmDialog
          title="Remove Integration?"
          message="The webhook token will be invalidated and all configuration removed. Existing leads will remain."
          confirmLabel="Remove"
          danger
          onConfirm={() => deleteMut.mutate(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      {/* Configure credentials modal */}
      {configTarget && (() => {
        const isMeta = configTarget.source === 'meta_facebook' || configTarget.source === 'meta_instagram';
        const cs = configTarget.credentials_status;
        return (
          <Modal title={`Configure: ${configTarget.source_display}`} onClose={() => setConfigTarget(null)} maxWidth="620px">
            <div className="flex flex-col gap-4">
              {isMeta ? (
                <>
                  {/* Callback URL + verify token to paste into Meta */}
                  <div style={{ background: '#eff6ff', border: '2px solid #1877f2', padding: '12px' }}>
                    <div className="font-heading font-black mb-2" style={{ fontSize: '0.82rem' }}>① Paste these into Meta</div>
                    <div style={{ fontSize: '0.7rem', color: '#555', marginBottom: '3px', fontWeight: 700 }}>Callback URL</div>
                    <div className="flex items-center gap-2 mb-2">
                      <div className="font-mono flex-1" style={{ fontSize: '0.7rem', wordBreak: 'break-all', background: '#fff', border: '1px solid #ccc', padding: '5px 7px' }}>{configTarget.webhook_url}</div>
                      <button onClick={() => copy(configTarget.webhook_url, 'm-url')}
                              style={{ fontSize: '0.62rem', border: '1px solid #000', background: copied === 'm-url' ? '#dcfce7' : '#fff', cursor: 'pointer', padding: '4px 7px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                        {copied === 'm-url' ? '✓' : 'Copy'}
                      </button>
                    </div>
                    <div style={{ fontSize: '0.7rem', color: '#555', marginBottom: '3px', fontWeight: 700 }}>Verify Token</div>
                    <div className="flex items-center gap-2">
                      <div className="font-mono flex-1" style={{ fontSize: '0.7rem', wordBreak: 'break-all', background: '#fff', border: '1px solid #ccc', padding: '5px 7px' }}>{creds.verify_token || '(set a verify token below)'}</div>
                      <button onClick={() => copy(creds.verify_token, 'm-vt')} disabled={!creds.verify_token}
                              style={{ fontSize: '0.62rem', border: '1px solid #000', background: copied === 'm-vt' ? '#dcfce7' : '#fff', cursor: 'pointer', padding: '4px 7px', fontWeight: 700 }}>
                        {copied === 'm-vt' ? '✓' : 'Copy'}
                      </button>
                    </div>
                  </div>

                  {/* Credential fields */}
                  <div className="font-heading font-black" style={{ fontSize: '0.82rem' }}>② Enter your Meta app credentials</div>
                  <div>
                    <Input label="Verify Token (you choose any string)" value={creds.verify_token}
                           onChange={e => setCreds(p => ({ ...p, verify_token: e.target.value }))}
                           placeholder="e.g. my_secret_verify_123" />
                    <button onClick={() => setCreds(p => ({ ...p, verify_token: `dlp_${Math.random().toString(36).slice(2, 14)}` }))}
                            style={{ fontSize: '0.66rem', border: 'none', background: 'none', color: '#1877f2', cursor: 'pointer', textDecoration: 'underline', marginTop: '4px' }}>
                      Generate one for me
                    </button>
                  </div>
                  <Input label={`App Secret ${cs?.has_app_secret ? '(saved — leave blank to keep)' : ''}`} type="password"
                         value={creds.app_secret} onChange={e => setCreds(p => ({ ...p, app_secret: e.target.value }))}
                         placeholder={cs?.has_app_secret ? '•••••••• (unchanged)' : 'From Meta App → Settings → Basic'} />
                  <Input label={`Page Access Token ${cs?.has_access_token ? '(saved — leave blank to keep)' : ''}`} type="password"
                         value={creds.access_token} onChange={e => setCreds(p => ({ ...p, access_token: e.target.value }))}
                         placeholder={cs?.has_access_token ? '•••••••• (unchanged)' : 'Long-lived Page access token'} />
                  <Input label="Facebook Page ID (for auto-fetching form fields)" value={creds.page_id}
                         onChange={e => setCreds(p => ({ ...p, page_id: e.target.value }))}
                         placeholder="e.g. 102938475610293" />

                  {/* ③ FIELD MAPPING */}
                  <div className="font-heading font-black flex items-center justify-between" style={{ fontSize: '0.82rem' }}>
                    <span>③ Map form fields → CRM fields</span>
                    <button onClick={fetchMetaFields}
                            className="btn-brutal btn-secondary px-2 py-1 font-heading font-bold"
                            style={{ fontSize: '0.66rem' }}>
                      ⟳ Fetch fields from Meta
                    </button>
                  </div>
                  <div style={{ fontSize: '0.72rem', color: '#666' }}>
                    Your Meta form questions may have any name. Map each to a CRM field so leads
                    sync correctly. Unmapped fields are still saved on the lead's raw data.
                  </div>
                  {metaFieldOptions.length > 0 && (
                    <datalist id="meta-field-options">
                      {metaFieldOptions.map(f => <option key={f} value={f} />)}
                    </datalist>
                  )}
                  <div className="flex flex-col gap-2">
                    {mapRows.map((row, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <input
                          list={metaFieldOptions.length ? 'meta-field-options' : undefined}
                          value={row.metaField}
                          onChange={e => setMapRows(rows => rows.map((r, j) => j === i ? { ...r, metaField: e.target.value } : r))}
                          placeholder="Meta field name"
                          className="input-brutal" style={{ flex: 1, fontSize: '0.75rem', boxShadow: '2px 2px 0 #000' }}
                        />
                        <span style={{ fontSize: '0.9rem' }}>→</span>
                        <select
                          value={row.target}
                          onChange={e => setMapRows(rows => rows.map((r, j) => j === i ? { ...r, target: e.target.value } : r))}
                          className="input-brutal" style={{ flex: 1, fontSize: '0.75rem', boxShadow: '2px 2px 0 #000' }}
                        >
                          <option value="">— Select CRM field —</option>
                          <optgroup label="Standard">
                            {STANDARD_TARGETS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                          </optgroup>
                          {(customFields ?? []).length > 0 && (
                            <optgroup label="Custom fields">
                              {(customFields ?? []).map(cf => (
                                <option key={cf.id} value={`custom:${cf.field_key}`}>{cf.name}</option>
                              ))}
                            </optgroup>
                          )}
                        </select>
                        <button onClick={() => setMapRows(rows => rows.filter((_, j) => j !== i))}
                                style={{ border: '2px solid #000', background: '#fee2e2', cursor: 'pointer', fontWeight: 900, padding: '4px 9px' }}>×</button>
                      </div>
                    ))}
                    <button onClick={() => setMapRows(rows => [...rows, { metaField: '', target: '' }])}
                            className="btn-brutal btn-yellow px-3 py-1.5 font-heading font-bold" style={{ fontSize: '0.72rem', alignSelf: 'flex-start' }}>
                      + Add field mapping
                    </button>
                  </div>

                  <div style={{ background: '#fffbee', border: '2px solid #ffe17c', padding: '10px 12px', fontSize: '0.72rem', lineHeight: 1.5 }}>
                    <strong>Setup steps in Meta:</strong><br />
                    1. developers.facebook.com → your App → <strong>Webhooks</strong> → subscribe to <strong>Page → leadgen</strong>.<br />
                    2. Paste the <strong>Callback URL</strong> and <strong>Verify Token</strong> above, click Verify &amp; Save.<br />
                    3. Connect your Facebook Page and generate a <strong>long-lived Page access token</strong>; paste it above.<br />
                    4. Add <strong>App Secret</strong> (App → Settings → Basic) so we can verify signatures.<br />
                    New Lead Ads form submissions will then appear in <strong>Leads</strong> automatically.
                  </div>
                </>
              ) : (
                <>
                  <div style={{ fontSize: '0.8rem', color: '#555' }}>
                    Paste the API key / credentials for {configTarget.source_display}.
                  </div>
                  <Input label={`API Key ${cs?.has_api_key ? '(saved — leave blank to keep)' : ''}`} type="password"
                         value={creds.api_key} onChange={e => setCreds(p => ({ ...p, api_key: e.target.value }))}
                         placeholder={cs?.has_api_key ? '•••••••• (unchanged)' : 'Provider API key'} />
                  <div style={{ background: '#f9f9f9', border: '2px solid #e5e5e5', padding: '8px 10px' }}>
                    <div style={{ fontSize: '0.66rem', color: '#888', fontWeight: 700, textTransform: 'uppercase', marginBottom: '4px' }}>Webhook URL</div>
                    <div className="font-mono" style={{ fontSize: '0.68rem', wordBreak: 'break-all' }}>{configTarget.webhook_url}</div>
                  </div>
                </>
              )}
            </div>

            <div className="flex gap-3 mt-5 pt-4" style={{ borderTop: '2px solid #eee' }}>
              <button onClick={() => setConfigTarget(null)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
              <button onClick={() => configureMut.mutate()} disabled={configureMut.isPending}
                      className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: '5px 5px 0 #000' }}>
                {configureMut.isPending ? '◌ Saving…' : 'Save Credentials →'}
              </button>
            </div>
          </Modal>
        );
      })()}
    </div>
  );
}
