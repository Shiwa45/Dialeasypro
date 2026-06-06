// ============================================================
// DialEasypro — Layout (Sidebar + Topbar + Main)
// ============================================================
import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api';
import { useToast } from './ui';

const NAV = [
  { path: '/dashboard',       icon: '◈', label: 'Dashboard'       },
  { path: '/leads',           icon: '◎', label: 'Leads'           },
  { path: '/calls',           icon: '☎', label: 'Calls'           },
  { path: '/queues',          icon: '▤', label: 'Call Queues'     },
  { path: '/agents',          icon: '◉', label: 'Agents'          },
  { path: '/communications',  icon: '✉', label: 'Communications'  },
  { path: '/campaigns',       icon: '▣', label: 'Campaigns'       },
  { path: '/reports',         icon: '▦', label: 'Reports'         },
  { path: '/integrations',    icon: '⊕', label: 'Integrations'    },
  { path: '/settings',        icon: '⚙', label: 'Settings'        },
];

function Sidebar({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const location = useLocation();
  const { agent, logout } = useAuthStore();
  const navigate = useNavigate();
  const { showToast } = useToast();

  const handleLogout = async () => {
    try {
      const refresh = localStorage.getItem('refresh_token');
      if (refresh) await authApi.logout(refresh);
    } catch {}
    logout();
    navigate('/login');
    showToast('info', 'Signed out', 'See you next time!');
  };

  return (
    <aside style={{
      width: collapsed ? '60px' : '220px',
      minWidth: collapsed ? '60px' : '220px',
      background: '#171e19',
      borderRight: '2px solid #000',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.2s ease, min-width 0.2s ease',
      overflow: 'hidden',
    }}>
      {/* Logo */}
      <div style={{ borderBottom: '2px solid rgba(255,255,255,0.08)', padding: collapsed ? '14px 0' : '14px 16px' }}
           className="flex items-center gap-3">
        <div style={{ width: '34px', height: '34px', background: '#ffe17c', border: '2px solid #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Space Grotesk', fontWeight: 900, fontSize: '1rem', flexShrink: 0, marginLeft: collapsed ? 'auto' : '0', marginRight: collapsed ? 'auto' : '0' }}>
          D
        </div>
        {!collapsed && (
          <div>
            <div className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '0.95rem', lineHeight: 1.1 }}>DialEasypro</div>
            <div style={{ color: '#b7c6c2', fontSize: '0.62rem', fontWeight: 600, letterSpacing: '0.06em' }}>ADMIN CRM</div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, paddingTop: '8px', overflowY: 'auto' }}>
        {NAV.map((item) => {
          const active = location.pathname.startsWith(item.path);
          return (
            <Link key={item.path} to={item.path} style={{ textDecoration: 'none' }}>
              <div className={`sidebar-item ${active ? 'active' : ''}`}
                   style={{ justifyContent: collapsed ? 'center' : 'flex-start', paddingLeft: collapsed ? '0' : '14px' }}
                   title={collapsed ? item.label : undefined}>
                <span style={{ fontSize: '1rem', flexShrink: 0 }}>{item.icon}</span>
                {!collapsed && <span style={{ whiteSpace: 'nowrap' }}>{item.label}</span>}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Agent + collapse */}
      <div style={{ borderTop: '2px solid rgba(255,255,255,0.08)' }}>
        {!collapsed && agent && (
          <div style={{ padding: '12px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <div className="font-heading font-bold" style={{ color: '#fff', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{agent.name}</div>
            <div style={{ color: '#b7c6c2', fontSize: '0.68rem', marginTop: '1px' }}>{agent.role.toUpperCase()}</div>
          </div>
        )}
        <button onClick={handleLogout} className="sidebar-item w-full"
                style={{ justifyContent: collapsed ? 'center' : 'flex-start', color: '#ff6b6b', border: 'none', background: 'none', cursor: 'pointer', width: '100%' }}>
          <span>⏻</span>
          {!collapsed && <span>Sign Out</span>}
        </button>
        <button onClick={onToggle} className="sidebar-item w-full"
                style={{ justifyContent: collapsed ? 'center' : 'flex-start', border: 'none', background: 'none', cursor: 'pointer', width: '100%' }}>
          <span style={{ transform: collapsed ? 'rotate(180deg)' : 'none', display: 'inline-block', transition: 'transform 0.2s' }}>◁</span>
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}

function Topbar({ title, onMenuClick }: { title: string; onMenuClick: () => void }) {
  const { agent } = useAuthStore();
  const navigate = useNavigate();

  return (
    <header style={{ borderBottom: '2px solid #000', background: '#fff', padding: '0 20px', height: '56px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
      <div className="flex items-center gap-3">
        <button onClick={onMenuClick} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.2rem', display: 'none' }}
                className="md:hidden">☰</button>
        <div className="font-heading font-black" style={{ fontSize: '1rem' }}>{title}</div>
      </div>
      <div className="flex items-center gap-3">
        <button className="btn-brutal btn-secondary px-3 py-1.5 font-heading font-bold" style={{ fontSize: '0.75rem' }}
                onClick={() => navigate('/profile')}>
          {agent?.name?.split(' ')[0] ?? 'Agent'} ↗
        </button>
        <div style={{ width: '32px', height: '32px', background: '#ffe17c', border: '2px solid #000', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'Space Grotesk', fontWeight: 900, fontSize: '0.85rem', cursor: 'pointer' }}
             onClick={() => navigate('/profile')}>
          {agent?.name?.split(' ').map(n => n[0]).join('').slice(0,2) ?? 'A'}
        </div>
      </div>
    </header>
  );
}

const PAGE_TITLES: Record<string, string> = {
  '/dashboard': 'Dashboard', '/leads': 'Leads', '/calls': 'Calls',
  '/queues': 'Call Queues',
  '/agents': 'Agents', '/communications': 'Communications', '/campaigns': 'Campaigns',
  '/reports': 'Reports', '/integrations': 'Integrations', '/settings': 'Settings',
  '/profile': 'My Profile',
};

export function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const title = Object.entries(PAGE_TITLES).find(([p]) => location.pathname.startsWith(p))?.[1] ?? 'DialEasypro';

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <Topbar title={title} onMenuClick={() => setCollapsed(c => !c)} />
        <main style={{ flex: 1, overflowY: 'auto', background: '#f5f4f0' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
