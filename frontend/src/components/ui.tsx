// ============================================================
// DialEasypro — Shared UI Components
// ============================================================
import React, { useEffect, useRef, useState, useCallback } from 'react';

// ---- Modal ------------------------------------------------
interface ModalProps {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
}
export function Modal({ title, subtitle, onClose, children, maxWidth = '540px' }: ModalProps) {
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', esc);
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', esc); document.body.style.overflow = ''; };
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal-box" style={{ maxWidth, width: '100%' }}>
        <div className="flex items-center justify-between px-5 py-4 border-b-2 border-black"
             style={{ background: '#171e19' }}>
          <div>
            <h3 className="font-heading font-black" style={{ color: '#ffe17c', fontSize: '1rem' }}>{title}</h3>
            {subtitle && <p style={{ color: '#b7c6c2', fontSize: '0.75rem', marginTop: '2px' }}>{subtitle}</p>}
          </div>
          <button onClick={onClose} className="btn-brutal btn-secondary px-2 py-1 font-heading font-black"
                  style={{ fontSize: '0.9rem', lineHeight: 1 }}>✕</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

// ---- Toast System -----------------------------------------
export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: string;
  type: ToastType;
  title: string;
  message: string;
}

interface ToastCtx {
  showToast: (type: ToastType, title: string, message: string) => void;
}

export const ToastContext = React.createContext<ToastCtx>({ showToast: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((type: ToastType, title: string, message: string) => {
    const id = `t_${Date.now()}_${Math.random()}`;
    setToasts((p) => [...p, { id, type, title, message }]);
    setTimeout(() => setToasts((p) => p.filter((t) => t.id !== id)), 4000);
  }, []);

  const colors: Record<ToastType, { bar: string; icon: string }> = {
    success: { bar: '#22c55e', icon: '✓' },
    error:   { bar: '#ef4444', icon: '✕' },
    warning: { bar: '#f59e0b', icon: '⚠' },
    info:    { bar: '#3b82f6', icon: 'ℹ' },
  };

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className="toast">
            <div style={{ height: '4px', background: colors[t.type].bar }} />
            <div className="flex items-start gap-3 p-3">
              <span className="font-heading font-black text-sm" style={{ color: colors[t.type].bar }}>
                {colors[t.type].icon}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-heading font-black" style={{ fontSize: '0.82rem' }}>{t.title}</div>
                <div className="font-medium" style={{ fontSize: '0.75rem', color: '#555', marginTop: '2px' }}>{t.message}</div>
              </div>
              <button onClick={() => setToasts((p) => p.filter((x) => x.id !== t.id))}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999', fontSize: '0.85rem' }}>✕</button>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return React.useContext(ToastContext);
}

// ---- Status Badge -----------------------------------------
const STATUS_COLORS: Record<string, string> = {
  new: 'status-new', attempted: 'status-new', contacted: 'status-new',
  interested: 'status-interested', follow_up: 'status-interested',
  negotiation: 'status-negotiation',
  converted: 'status-converted', active: 'status-active',
  lost: 'status-lost', not_interested: 'status-lost', duplicate: 'status-inactive',
  inactive: 'status-inactive', trial: 'status-trial',
  pending: 'status-new', approved: 'status-converted',
  rejected: 'status-lost',
};

export function StatusBadge({ status, label }: { status: string; label?: string }) {
  const cls = STATUS_COLORS[status] ?? 'status-inactive';
  return (
    <span className={`badge ${cls}`}>
      {label ?? status.replace(/_/g, ' ')}
    </span>
  );
}

// ---- Priority Badge ----------------------------------------
const PRIORITY_COLORS: Record<string, string> = {
  hot: 'background:#ef4444;color:#fff;border-color:#ef4444',
  high: 'background:#f97316;color:#fff;border-color:#f97316',
  medium: 'background:#ffe17c;color:#000;border-color:#000',
  low: 'background:#e5e7eb;color:#374151;border-color:#9ca3af',
};
export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className="badge" style={{ ...Object.fromEntries(
      PRIORITY_COLORS[priority]?.split(';').map(s => { const [k,v] = s.split(':'); return [k.trim().replace(/-([a-z])/g, (_,c)=>c.toUpperCase()), v?.trim()]; }) ?? []
    ) }}>
      {priority === 'hot' ? '🔥 ' : ''}{priority.toUpperCase()}
    </span>
  );
}

// ---- Pagination --------------------------------------------
interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (p: number) => void;
}
export function Pagination({ page, totalPages, onPageChange }: PaginationProps) {
  if (totalPages <= 1) return null;
  const pages = Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
    if (totalPages <= 7) return i + 1;
    if (page <= 4) return i + 1 <= 5 ? i + 1 : i === 5 ? -1 : totalPages;
    if (page >= totalPages - 3) return i === 0 ? 1 : i === 1 ? -1 : totalPages - 5 + i;
    return i === 0 ? 1 : i === 1 ? -1 : i === 5 ? -2 : i === 6 ? totalPages : page - 3 + i;
  });
  return (
    <div className="flex items-center gap-1 justify-end mt-4">
      <button onClick={() => onPageChange(page - 1)} disabled={page === 1}
              className="btn-brutal btn-secondary px-3 py-1.5 font-heading font-bold text-xs" style={{ fontSize: '0.75rem' }}>← Prev</button>
      {pages.map((p, i) =>
        p < 0 ? <span key={`e${i}`} className="px-2 font-heading font-bold text-xs">…</span> :
        <button key={p} onClick={() => onPageChange(p)}
                className="btn-brutal px-3 py-1.5 font-heading font-bold"
                style={{ fontSize: '0.75rem', background: p === page ? '#ffe17c' : '#fff', boxShadow: p === page ? '3px 3px 0 #000' : '2px 2px 0 #000' }}>
          {p}
        </button>
      )}
      <button onClick={() => onPageChange(page + 1)} disabled={page === totalPages}
              className="btn-brutal btn-secondary px-3 py-1.5 font-heading font-bold text-xs" style={{ fontSize: '0.75rem' }}>Next →</button>
    </div>
  );
}

// ---- Loading Spinner ---------------------------------------
export function Spinner({ size = 40 }: { size?: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '40px' }}>
      <div style={{
        width: size, height: size,
        border: '3px solid #e5e5e5',
        borderTop: '3px solid #ffe17c',
        borderRadius: '50%',
        animation: 'spin 0.7s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ---- Empty State -------------------------------------------
export function EmptyState({ icon = '○', title, message, action }: {
  icon?: string; title: string; message?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="font-heading font-black" style={{ fontSize: '3rem', marginBottom: '16px', opacity: 0.3 }}>{icon}</div>
      <div className="font-heading font-black" style={{ fontSize: '1.1rem', marginBottom: '6px' }}>{title}</div>
      {message && <p className="font-medium" style={{ fontSize: '0.82rem', color: '#666', maxWidth: '300px', marginBottom: '20px' }}>{message}</p>}
      {action && (
        <button onClick={action.onClick}
                className="btn-brutal btn-primary px-5 py-2.5 font-heading font-black"
                style={{ fontSize: '0.85rem' }}>
          {action.label}
        </button>
      )}
    </div>
  );
}

// ---- Confirm Dialog ----------------------------------------
export function ConfirmDialog({ title, message, confirmLabel = 'Confirm', danger = false, onConfirm, onCancel }: {
  title: string; message: string; confirmLabel?: string;
  danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <div className="modal-overlay">
      <div className="modal-box" style={{ maxWidth: '400px' }}>
        <div className="p-5 border-b-2 border-black" style={{ background: danger ? '#ef4444' : '#171e19' }}>
          <h3 className="font-heading font-black" style={{ color: '#fff', fontSize: '1rem' }}>{title}</h3>
        </div>
        <div className="p-5">
          <p className="font-medium" style={{ fontSize: '0.875rem', lineHeight: 1.6, marginBottom: '20px' }}>{message}</p>
          <div className="flex gap-3">
            <button onClick={onCancel} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black" style={{ fontSize: '0.85rem' }}>Cancel</button>
            <button onClick={onConfirm}
                    className="btn-brutal flex-1 py-2.5 font-heading font-black"
                    style={{ background: danger ? '#ef4444' : '#000', color: '#fff', border: '2px solid #000', boxShadow: '4px 4px 0 #000', fontSize: '0.85rem' }}>
              {confirmLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---- Input -----------------------------------------------
export function Input({ label, required, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label?: string; required?: boolean }) {
  return (
    <div>
      {label && <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>{label}{required && ' *'}</label>}
      <input className="input-brutal" {...props} />
    </div>
  );
}

export function Select({ label, required, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement> & { label?: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div>
      {label && <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>{label}{required && ' *'}</label>}
      <select className="input-brutal" style={{ cursor: 'pointer' }} {...props}>{children}</select>
    </div>
  );
}

export function Textarea({ label, required, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: string; required?: boolean }) {
  return (
    <div>
      {label && <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>{label}{required && ' *'}</label>}
      <textarea className="input-brutal" rows={3} {...props} />
    </div>
  );
}

// ---- Stat Card ---------------------------------------------
type StatTone = 'yellow' | 'green' | 'blue' | 'red' | 'purple' | 'teal';

const STAT_TONES: Record<StatTone, {
  background: string;
  value: string;
  label: string;
  sub: string;
  icon: string;
}> = {
  yellow: { background: '#fff1a8', value: '#000000', label: '#3b3100', sub: '#655400', icon: '#c28b00' },
  green:  { background: '#dcfce7', value: '#064e3b', label: '#14532d', sub: '#166534', icon: '#16a34a' },
  blue:   { background: '#dbeafe', value: '#1e3a8a', label: '#1e40af', sub: '#2563eb', icon: '#3b82f6' },
  red:    { background: '#fee2e2', value: '#7f1d1d', label: '#991b1b', sub: '#b91c1c', icon: '#ef4444' },
  purple: { background: '#ede9fe', value: '#4c1d95', label: '#5b21b6', sub: '#6d28d9', icon: '#8b5cf6' },
  teal:   { background: '#ccfbf1', value: '#134e4a', label: '#115e59', sub: '#0f766e', icon: '#14b8a6' },
};

export function StatCard({ label, value, sub, accent = false, icon, tone }: {
  label: string; value: string | number; sub?: string; accent?: boolean; icon?: string; tone?: StatTone;
}) {
  const colors = tone ? STAT_TONES[tone] : undefined;

  return (
    <div className="stat-card" style={{ background: colors?.background }}>
      <div className="flex items-start justify-between mb-2">
        <div className="font-heading font-bold" style={{ fontSize: '0.7rem', color: colors?.label ?? '#666', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</div>
        {icon && <span style={{ fontSize: '1.1rem', color: colors?.icon, opacity: tone ? 0.9 : 0.5 }}>{icon}</span>}
      </div>
      <div className="font-heading font-black" style={{ fontSize: '1.9rem', lineHeight: 1, color: colors?.value, background: accent && !tone ? '#ffe17c' : 'transparent', display: 'inline-block', padding: accent && !tone ? '2px 6px' : '0', border: accent && !tone ? '2px solid #000' : 'none' }}>
        {value}
      </div>
      {sub && <div className="font-medium mt-1" style={{ fontSize: '0.75rem', color: colors?.sub ?? '#888' }}>{sub}</div>}
    </div>
  );
}

// ---- Section Header ----------------------------------------
export function SectionHeader({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h2 className="font-heading font-black" style={{ fontSize: '1.4rem' }}>{title}</h2>
        {sub && <p className="font-medium" style={{ fontSize: '0.8rem', color: '#666', marginTop: '2px' }}>{sub}</p>}
      </div>
      {children && <div className="flex gap-2 flex-wrap">{children}</div>}
    </div>
  );
}

// ---- Score Bar ---------------------------------------------
export function ScoreBar({ score }: { score: number }) {
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-2">
      <div className="progress-bar" style={{ width: '60px' }}>
        <div className="progress-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="font-mono font-bold" style={{ fontSize: '0.72rem' }}>{score}</span>
    </div>
  );
}

// ---- Date filter bar ---
export function DateFilter({ dateFrom, dateTo, onDateFrom, onDateTo }: {
  dateFrom: string; dateTo: string;
  onDateFrom: (v: string) => void; onDateTo: (v: string) => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <input type="date" value={dateFrom} onChange={e => onDateFrom(e.target.value)}
             className="input-brutal" style={{ width: 'auto', padding: '6px 10px', fontSize: '0.8rem', boxShadow: '2px 2px 0 #000' }} />
      <span className="font-heading font-bold text-xs">to</span>
      <input type="date" value={dateTo} onChange={e => onDateTo(e.target.value)}
             className="input-brutal" style={{ width: 'auto', padding: '6px 10px', fontSize: '0.8rem', boxShadow: '2px 2px 0 #000' }} />
    </div>
  );
}
