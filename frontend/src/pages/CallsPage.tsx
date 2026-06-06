import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { callsApi } from '../api';
import {
  SectionHeader, Spinner, EmptyState, Pagination, StatCard, useToast,
} from '../components/ui';
import { fmtRelative, formatDuration } from '../utils/fmt';

export default function Calls() {
  const nav = useNavigate();
  const { showToast } = useToast();
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ direction: '', connected: '', date_from: '', date_to: '' });

  const { data, isLoading } = useQuery({
    queryKey: ['calls', page, filters],
    queryFn: () => callsApi.list({
      page, page_size: 25,
      direction: filters.direction || undefined,
      connected: filters.connected || undefined,
      date_from: filters.date_from || undefined,
      date_to: filters.date_to || undefined,
    }).then(r => r.data),
    placeholderData: prev => prev,
  });

  const { data: stats } = useQuery({
    queryKey: ['call-stats'],
    queryFn: () => callsApi.stats().then(r => r.data),
    refetchInterval: 30000,
  });

  const clickToCallMut = useMutation({
    mutationFn: ({ lead_id }: { lead_id: number }) => callsApi.clickToCall(lead_id),
    onSuccess: () => showToast('success', 'Call initiated!', 'Your phone will ring first, then the lead.'),
    onError: () => showToast('error', 'Call failed', 'Check your calling integration settings.'),
  });

  const calls = data?.results ?? [];

  const filterSet = (k: string) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) =>
    setFilters(p => ({ ...p, [k]: e.target.value }));

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Call Log" sub={`${data?.count ?? 0} calls`}>
        <button onClick={() => nav('/leads')} className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          ☎ Go to Lead
        </button>
        <button onClick={() => nav('/leads/import')} className="btn-brutal btn-secondary px-4 py-2 font-heading font-bold"
                style={{ fontSize: '0.82rem', boxShadow: '3px 3px 0 #000' }}>
          ▦ Call Stats →
        </button>
      </SectionHeader>

      {/* Today stats */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))' }}>
        <StatCard label="Today Total" value={stats?.today.total ?? 0} icon="☎" accent />
        <StatCard label="Today Connected" value={stats?.today.connected ?? 0} icon="✓" />
        <StatCard label="Today Talk Time" value={formatDuration(stats?.today.total_duration_seconds ?? 0)} icon="⏱" />
        <StatCard label="Connection Rate" value={`${stats?.period.connection_rate ?? 0}%`} icon="%" />
        <StatCard label="Avg Duration" value={formatDuration(stats?.period.avg_duration_seconds ?? 0)} icon="⏱" />
        <StatCard label="Total Cost" value={`₹${stats?.period.total_cost_rupees?.toFixed(2) ?? 0}`} icon="₹" />
      </div>

      {/* Filters */}
      <div className="card card-sm p-3 flex flex-wrap items-center gap-2">
        <select value={filters.direction} onChange={filterSet('direction')} className="input-brutal" style={{ width: 'auto', boxShadow: '2px 2px 0 #000' }}>
          <option value="">All Directions</option>
          <option value="outbound">↗ Outbound</option>
          <option value="inbound">↙ Inbound</option>
        </select>
        <select value={filters.connected} onChange={filterSet('connected')} className="input-brutal" style={{ width: 'auto', boxShadow: '2px 2px 0 #000' }}>
          <option value="">All Calls</option>
          <option value="true">Connected</option>
          <option value="false">Not Connected</option>
        </select>
        <input type="date" value={filters.date_from} onChange={filterSet('date_from')} className="input-brutal" style={{ width: 'auto', fontSize: '0.8rem', boxShadow: '2px 2px 0 #000' }} />
        <span className="font-heading font-bold text-xs">to</span>
        <input type="date" value={filters.date_to} onChange={filterSet('date_to')} className="input-brutal" style={{ width: 'auto', fontSize: '0.8rem', boxShadow: '2px 2px 0 #000' }} />
        {Object.values(filters).some(Boolean) && (
          <button onClick={() => setFilters({ direction: '', connected: '', date_from: '', date_to: '' })}
                  className="btn-brutal btn-secondary px-3 py-1.5 font-heading font-bold" style={{ fontSize: '0.75rem' }}>
            Clear
          </button>
        )}
      </div>

      {isLoading ? <Spinner /> : calls.length === 0 ? (
        <EmptyState icon="☎" title="No calls found" message="Call logs will appear here." />
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="table-brutal">
            <thead>
              <tr>
                {['Dir', 'Agent', 'Lead', 'Phone', 'Duration', 'Status', 'Disposition', 'Recording', 'When', 'Actions'].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {calls.map(c => (
                <tr key={c.id}>
                  <td>
                    <span style={{ fontSize: '1.1rem', color: c.direction === 'outbound' ? '#3b82f6' : '#22c55e' }}>
                      {c.direction === 'outbound' ? '↗' : '↙'}
                    </span>
                  </td>
                  <td style={{ fontSize: '0.8rem' }}>{c.agent_name ?? '—'}</td>
                  <td>
                    {c.lead ? (
                      <button onClick={() => nav(`/leads/${c.lead}`)}
                              style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.8rem', fontFamily: 'Space Grotesk', fontWeight: 700, textDecoration: 'underline' }}>
                        {c.lead_name}
                      </button>
                    ) : <span style={{ color: '#ccc' }}>—</span>}
                  </td>
                  <td className="font-mono" style={{ fontSize: '0.78rem' }}>{c.phone_number}</td>
                  <td className="font-heading font-black" style={{ fontSize: '0.82rem' }}>{c.duration_display}</td>
                  <td>
                    {c.is_connected
                      ? <span className="badge status-active">Connected</span>
                      : <span className="badge status-inactive">No Answer</span>}
                  </td>
                  <td>{c.disposition_name ? <span className="tag">{c.disposition_name}</span> : <span style={{ color: '#ccc' }}>—</span>}</td>
                  <td>
                    {c.recording?.playback_url
                      ? <audio controls preload="none" src={c.recording.playback_url} style={{ height: '32px', maxWidth: '180px' }} />
                      : <span style={{ color: '#ccc', fontSize: '0.72rem' }}>—</span>}
                  </td>
                  <td style={{ fontSize: '0.72rem', color: '#888' }}>{fmtRelative(c.started_at)}</td>
                  <td>
                    <div className="flex gap-1">
                      {c.lead && (
                        <button onClick={() => clickToCallMut.mutate({ lead_id: c.lead! })}
                                className="btn-brutal btn-primary px-2 py-1 font-heading font-bold" style={{ fontSize: '0.65rem' }}>
                          ☎ Call
                        </button>
                      )}
                      {c.lead && (
                        <button onClick={() => nav(`/leads/${c.lead}`)}
                                className="btn-brutal btn-yellow px-2 py-1 font-heading font-bold" style={{ fontSize: '0.65rem' }}>
                          View
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
    </div>
  );
}
