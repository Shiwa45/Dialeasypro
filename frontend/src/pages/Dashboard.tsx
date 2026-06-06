import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { leadsApi, reportsApi } from '../api';
import { StatCard, Spinner, StatusBadge, ScoreBar } from '../components/ui';
import { fmtDate } from '../utils/fmt';

export default function Dashboard() {
  const nav = useNavigate();

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['lead-stats'],
    queryFn: () => leadsApi.stats().then(r => r.data),
    refetchInterval: 60_000,
  });
  const { data: daily } = useQuery({
    queryKey: ['daily-activity'],
    queryFn: () => reportsApi.dailyActivity().then(r => r.data),
    refetchInterval: 30_000,
  });
  const { data: callAnalytics } = useQuery({
    queryKey: ['call-analytics-dashboard'],
    queryFn: () => reportsApi.callAnalytics().then(r => r.data),
  });
  const { data: recentLeads } = useQuery({
    queryKey: ['leads-recent'],
    queryFn: () => leadsApi.list({ page: 1, page_size: 6, order_by: '-created_at' }).then(r => r.data),
  });
  const { data: funnel } = useQuery({
    queryKey: ['funnel-dashboard'],
    queryFn: () => reportsApi.conversionFunnel().then(r => r.data),
  });

  if (statsLoading) return <Spinner />;

  const trendData = callAnalytics?.daily_trend?.slice(-14) ?? [];

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="font-heading font-black" style={{ fontSize: '1.5rem' }}>Dashboard</h2>
          <p className="font-medium" style={{ fontSize: '0.8rem', color: '#666' }}>
            {new Date().toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </p>
        </div>
        <button onClick={() => nav('/leads?status=new')}
                className="btn-brutal btn-primary px-4 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem', boxShadow: '5px 5px 0 #000' }}>
          + New Lead
        </button>
      </div>

      {/* KPI row */}
      <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))' }}>
        <StatCard label="New Leads Today" value={daily?.leads.new_today ?? 0} icon="◎" tone="yellow" />
        <StatCard label="Total Active Leads" value={stats?.total.active_leads ?? 0} icon="○" tone="green" />
        <StatCard label="Calls Today" value={daily?.calls.total ?? 0}
                  sub={`${daily?.calls.connected ?? 0} connected`} icon="☎" tone="blue" />
        <StatCard label="Follow-ups Due" value={daily?.followups.due_today ?? 0}
                  sub={`${daily?.leads.overdue_followups ?? 0} overdue`} icon="⏰" tone="red" />
        <StatCard label="Conversion Rate" value={`${stats?.total.conversion_rate ?? 0}%`} icon="%" tone="purple" />
        <StatCard label="Pipeline Value"
                  value={`₹${((stats?.total.pipeline_value ?? 0) / 100000).toFixed(1)}L`} icon="₹" tone="teal" />
      </div>

      <div className="grid gap-5" style={{ gridTemplateColumns: '2fr 1fr' }}>
        {/* Call trend chart */}
        <div className="card p-4">
          <div className="font-heading font-black mb-4" style={{ fontSize: '0.9rem' }}>
            ▸ Call Activity — Last 14 Days
          </div>
          {trendData.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={trendData}>
                <defs>
                  <linearGradient id="gTotal" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ffe17c" stopOpacity={0.6} />
                    <stop offset="95%" stopColor="#ffe17c" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gConn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                <XAxis dataKey="date" tick={{ fontSize: 10, fontFamily: 'Space Grotesk' }}
                       tickFormatter={(v) => v.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip contentStyle={{ border: '2px solid #000', borderRadius: 0, fontFamily: 'Space Grotesk', fontSize: '0.75rem' }} />
                <Area type="monotone" dataKey="total" name="Total Calls" stroke="#ffe17c" strokeWidth={2} fill="url(#gTotal)" />
                <Area type="monotone" dataKey="connected" name="Connected" stroke="#22c55e" strokeWidth={2} fill="url(#gConn)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-40" style={{ color: '#999', fontSize: '0.82rem' }}>No call data yet</div>
          )}
        </div>

        {/* Conversion funnel */}
        <div className="card p-4">
          <div className="font-heading font-black mb-4" style={{ fontSize: '0.9rem' }}>▸ Pipeline Funnel</div>
          {(funnel?.funnel ?? []).length === 0 ? (
            <div className="flex items-center justify-center h-40" style={{ color: '#999', fontSize: '0.82rem' }}>No pipeline data yet</div>
          ) : (
            <div className="flex flex-col gap-2">
              {(funnel?.funnel ?? []).map((stage) => (
                <div key={stage.status}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-medium" style={{ fontSize: '0.72rem', color: '#555' }}>{stage.label}</span>
                    <span className="font-heading font-black" style={{ fontSize: '0.78rem' }}>{stage.count}</span>
                  </div>
                  <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${stage.pct_of_total}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent leads */}
      <div className="card">
        <div className="px-5 py-3 border-b-2 border-black flex items-center justify-between" style={{ background: '#171e19' }}>
          <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.9rem' }}>▸ Recent Leads</span>
          <button onClick={() => nav('/leads')}
                  className="btn-brutal btn-yellow px-3 py-1 font-heading font-bold"
                  style={{ fontSize: '0.72rem', boxShadow: '2px 2px 0 #000' }}>
            View All →
          </button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="table-brutal">
            <thead>
              <tr>
                {['Lead', 'Phone', 'Source', 'Status', 'Score', 'Assigned To', 'Created'].map(h => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(recentLeads?.results ?? []).map((lead) => (
                <tr key={lead.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/leads/${lead.id}`)}>
                  <td>
                    <div className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{lead.name}</div>
                    <div style={{ fontSize: '0.72rem', color: '#888' }}>{lead.city}</div>
                  </td>
                  <td className="font-mono" style={{ fontSize: '0.78rem' }}>{lead.phone}</td>
                  <td><span className="tag">{lead.source_display}</span></td>
                  <td><StatusBadge status={lead.status} label={lead.status_display} /></td>
                  <td><ScoreBar score={lead.score} /></td>
                  <td style={{ fontSize: '0.8rem' }}>{lead.assigned_to_name ?? '—'}</td>
                  <td style={{ fontSize: '0.75rem', color: '#888' }}>{fmtDate(lead.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
