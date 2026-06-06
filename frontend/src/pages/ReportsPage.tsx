import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi } from '../api';
import { SectionHeader, Spinner, StatCard, DateFilter } from '../components/ui';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, Legend, AreaChart, Area,
} from 'recharts';
import { formatDuration } from '../utils/fmt';

const COLORS = ['#ffe17c', '#171e19', '#b7c6c2', '#22c55e', '#ef4444', '#3b82f6', '#f97316', '#8b5cf6'];
const today = new Date().toISOString().slice(0, 10);
const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);

type Tab = 'agents' | 'sources' | 'calls' | 'funnel';

export default function Reports() {
  const [tab, setTab] = useState<Tab>('agents');
  const [dateFrom, setDateFrom] = useState(thirtyDaysAgo);
  const [dateTo, setDateTo] = useState(today);

  const params = { date_from: dateFrom, date_to: dateTo };

  const agentQ = useQuery({ queryKey: ['r-agents', dateFrom, dateTo], queryFn: () => reportsApi.agentPerformance(params).then(r => r.data), enabled: tab === 'agents' });
  const sourceQ = useQuery({ queryKey: ['r-sources', dateFrom, dateTo], queryFn: () => reportsApi.leadSources(params).then(r => r.data), enabled: tab === 'sources' });
  const callQ = useQuery({ queryKey: ['r-calls', dateFrom, dateTo], queryFn: () => reportsApi.callAnalytics(params).then(r => r.data), enabled: tab === 'calls' });
  const funnelQ = useQuery({ queryKey: ['r-funnel', dateFrom, dateTo], queryFn: () => reportsApi.conversionFunnel(params).then(r => r.data), enabled: tab === 'funnel' });

  const TABS: { k: Tab; l: string }[] = [
    { k: 'agents', l: '◉ Agent Performance' },
    { k: 'sources', l: '◎ Lead Sources' },
    { k: 'calls', l: '☎ Call Analytics' },
    { k: 'funnel', l: '▸ Conversion Funnel' },
  ];

  const isLoading = agentQ.isLoading || sourceQ.isLoading || callQ.isLoading || funnelQ.isLoading;

  const TOOLTIP_STYLE = { border: '2px solid #000', borderRadius: 0, fontFamily: 'Space Grotesk', fontSize: '0.75rem' };

  return (
    <div className="p-6 flex flex-col gap-4" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Reports & Analytics">
        <DateFilter dateFrom={dateFrom} dateTo={dateTo} onDateFrom={setDateFrom} onDateTo={setDateTo} />
      </SectionHeader>

      <div style={{ display: 'flex', borderBottom: '2px solid #000', overflowX: 'auto' }}>
            {TABS.map(t => (
              <button key={t.k} onClick={() => setTab(t.k)} className="font-heading font-bold px-4 py-2.5"
                      style={{ background: tab === t.k ? '#ffe17c' : '#fff', border: 'none', borderRight: '2px solid #000', cursor: 'pointer', fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
                {t.l}
              </button>
            ))}
          </div>

          {isLoading && <Spinner />}

          {/* Agent Performance */}
          {tab === 'agents' && agentQ.data && !agentQ.isLoading && (
            <div className="flex flex-col gap-5">
              <div className="card" style={{ overflowX: 'auto' }}>
                <div className="px-4 py-3 border-b-2 border-black" style={{ background: '#171e19' }}>
                  <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.9rem' }}>
                    ▸ Agent Performance — {agentQ.data.period.date_from} to {agentQ.data.period.date_to}
                  </span>
                </div>
                <table className="table-brutal">
                  <thead>
                    <tr>
                      {['Agent', 'Role', 'Leads', 'Converted', 'Win %', 'Avg Score', 'Calls', 'Connected', 'Conn %', 'Talk Time'].map(h => <th key={h}>{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {agentQ.data.agents.map(a => (
                      <tr key={a.agent_id}>
                        <td className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{a.agent_name}</td>
                        <td><span className="tag">{a.agent_role}</span></td>
                        <td style={{ fontSize: '0.82rem' }}>{a.leads.total}</td>
                        <td className="font-heading font-black" style={{ fontSize: '0.82rem', color: '#22c55e' }}>{a.leads.converted}</td>
                        <td style={{ fontSize: '0.82rem' }}>{a.leads.conversion_rate}%</td>
                        <td style={{ fontSize: '0.82rem' }}>{Math.round(a.leads.avg_score)}</td>
                        <td style={{ fontSize: '0.82rem' }}>{a.calls.total}</td>
                        <td style={{ fontSize: '0.82rem' }}>{a.calls.connected}</td>
                        <td style={{ fontSize: '0.82rem' }}>{a.calls.connection_rate}%</td>
                        <td className="font-mono" style={{ fontSize: '0.78rem' }}>{formatDuration(a.calls.total_duration_seconds)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-5" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="card p-4">
                  <div className="font-heading font-black mb-3" style={{ fontSize: '0.9rem' }}>▸ Conversions by Agent</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={agentQ.data.agents}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                      <XAxis dataKey="agent_name" tick={{ fontSize: 10, fontFamily: 'Space Grotesk' }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Legend />
                      <Bar dataKey="leads.converted" name="Converted" fill="#22c55e" />
                      <Bar dataKey="leads.lost" name="Lost" fill="#ef4444" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="card p-4">
                  <div className="font-heading font-black mb-3" style={{ fontSize: '0.9rem' }}>▸ Calls by Agent</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={agentQ.data.agents}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                      <XAxis dataKey="agent_name" tick={{ fontSize: 10, fontFamily: 'Space Grotesk' }} />
                      <YAxis tick={{ fontSize: 10 }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Legend />
                      <Bar dataKey="calls.total" name="Total" fill="#ffe17c" />
                      <Bar dataKey="calls.connected" name="Connected" fill="#171e19" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {/* Lead Sources */}
          {tab === 'sources' && sourceQ.data && !sourceQ.isLoading && (
            <div className="grid gap-5" style={{ gridTemplateColumns: '3fr 2fr' }}>
              <div className="card" style={{ overflowX: 'auto' }}>
                <div className="px-4 py-3 border-b-2 border-black" style={{ background: '#171e19' }}>
                  <span className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.9rem' }}>▸ Leads by Source</span>
                </div>
                <table className="table-brutal">
                  <thead><tr>{['Source', 'Total', 'Converted', 'Lost', 'Conv %', 'Avg Score', 'Deal Value'].map(h => <th key={h}>{h}</th>)}</tr></thead>
                  <tbody>
                    {((sourceQ.data as { by_source: Array<{ source: string; source_display: string; total: number; converted: number; lost: number; conversion_rate: number; avg_score: number; total_deal_value: number }> }).by_source ?? []).map((s, i) => (
                      <tr key={s.source}>
                        <td><span className="tag" style={{ background: COLORS[i % COLORS.length], borderColor: '#000', color: i < 2 ? '#fff' : '#000' }}>{s.source_display}</span></td>
                        <td className="font-heading font-black" style={{ fontSize: '0.82rem' }}>{s.total}</td>
                        <td style={{ color: '#22c55e', fontWeight: 700, fontSize: '0.82rem' }}>{s.converted}</td>
                        <td style={{ color: '#ef4444', fontSize: '0.82rem' }}>{s.lost}</td>
                        <td style={{ fontSize: '0.82rem' }}>{s.conversion_rate}%</td>
                        <td style={{ fontSize: '0.82rem' }}>{s.avg_score}</td>
                        <td style={{ fontSize: '0.78rem' }}>₹{(s.total_deal_value / 100000).toFixed(1)}L</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="card p-4">
                <div className="font-heading font-black mb-3" style={{ fontSize: '0.9rem' }}>▸ Volume by Source</div>
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={(sourceQ.data as { by_source: Array<{ source_display: string; total: number }> }).by_source}
                      dataKey="total" nameKey="source_display" cx="50%" cy="50%" outerRadius={100}
                    >
                      {((sourceQ.data as { by_source: unknown[] }).by_source ?? []).map((_, i) => (
                        <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="#000" strokeWidth={2} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Call Analytics */}
          {tab === 'calls' && callQ.data && !callQ.isLoading && (
            <div className="flex flex-col gap-5">
              <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))' }}>
                <StatCard label="Total Calls" value={callQ.data.summary.total_calls} accent />
                <StatCard label="Connected" value={callQ.data.summary.connected_calls} />
                <StatCard label="Connection %" value={`${callQ.data.summary.connection_rate}%`} />
                <StatCard label="Avg Duration" value={formatDuration(callQ.data.summary.avg_duration_seconds)} />
                <StatCard label="Total Talk Time" value={formatDuration(callQ.data.summary.total_duration_seconds)} />
                <StatCard label="Total Cost" value={`₹${callQ.data.summary.total_cost_rupees.toFixed(2)}`} />
              </div>
              <div className="grid gap-5" style={{ gridTemplateColumns: '2fr 1fr' }}>
                <div className="card p-4">
                  <div className="font-heading font-black mb-3" style={{ fontSize: '0.9rem' }}>▸ Daily Call Trend</div>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={callQ.data.daily_trend}>
                      <defs>
                        <linearGradient id="gTotal" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ffe17c" stopOpacity={0.5} />
                          <stop offset="95%" stopColor="#ffe17c" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="gConn" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#22c55e" stopOpacity={0.4} />
                          <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
                      <XAxis dataKey="date" tick={{ fontSize: 9, fontFamily: 'Space Grotesk' }} tickFormatter={v => v.slice(5)} />
                      <YAxis tick={{ fontSize: 9 }} />
                      <Tooltip contentStyle={TOOLTIP_STYLE} />
                      <Legend />
                      <Area type="monotone" dataKey="total" name="Total" stroke="#ffe17c" fill="url(#gTotal)" strokeWidth={2} />
                      <Area type="monotone" dataKey="connected" name="Connected" stroke="#22c55e" fill="url(#gConn)" strokeWidth={2} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
                <div className="card p-4">
                  <div className="font-heading font-black mb-3" style={{ fontSize: '0.9rem' }}>▸ By Disposition</div>
                  {callQ.data.by_disposition.length === 0 ? (
                    <div style={{ color: '#999', fontSize: '0.8rem', textAlign: 'center', padding: '30px' }}>No disposition data</div>
                  ) : callQ.data.by_disposition.slice(0, 8).map((d) => (
                    <div key={d.disposition__name} className="mb-2">
                      <div className="flex justify-between mb-0.5">
                        <span style={{ fontSize: '0.72rem', color: '#555' }}>{d.disposition__name}</span>
                        <span className="font-heading font-black" style={{ fontSize: '0.72rem' }}>{d.count}</span>
                      </div>
                      <div className="progress-bar">
                        <div className="progress-fill" style={{ width: `${(d.count / callQ.data.by_disposition[0].count) * 100}%`, background: d.disposition__is_positive ? '#22c55e' : '#ef4444' }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Conversion Funnel */}
          {tab === 'funnel' && funnelQ.data && !funnelQ.isLoading && (
            <div className="grid gap-5" style={{ gridTemplateColumns: '2fr 1fr' }}>
              <div className="card p-5">
                <div className="font-heading font-black mb-4" style={{ fontSize: '0.95rem' }}>
                  ▸ Lead Conversion Funnel ({funnelQ.data.total} total leads)
                </div>
                {funnelQ.data.funnel.map((stage, i) => (
                  <div key={stage.status} className="mb-4">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>{stage.label}</span>
                      <div className="flex gap-3">
                        <span className="font-heading font-black" style={{ fontSize: '0.85rem' }}>{stage.count}</span>
                        <span style={{ fontSize: '0.75rem', color: '#888', minWidth: '36px', textAlign: 'right' }}>{stage.pct_of_total}%</span>
                      </div>
                    </div>
                    <div className="progress-bar">
                      <div className="progress-fill" style={{ width: `${stage.pct_of_total}%`, background: COLORS[i % COLORS.length] }} />
                    </div>
                  </div>
                ))}
              </div>
              <div className="card p-5 flex flex-col gap-3">
                <div className="font-heading font-black mb-2" style={{ fontSize: '0.95rem' }}>▸ Summary</div>
                <StatCard label="Total Leads" value={funnelQ.data.total} accent />
                <StatCard
                  label="Converted"
                  value={funnelQ.data.funnel.find(f => f.status === 'converted')?.count ?? 0}
                />
                <StatCard label="Lost" value={funnelQ.data.lost} />
                <StatCard
                  label="Win Rate"
                  value={`${funnelQ.data.total > 0
                    ? Math.round(((funnelQ.data.funnel.find(f => f.status === 'converted')?.count ?? 0) / funnelQ.data.total) * 100)
                    : 0}%`}
                />
              </div>
            </div>
          )}
    </div>
  );
}
