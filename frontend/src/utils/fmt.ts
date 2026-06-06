// DialEasypro — Utility formatters
import { format, formatDistanceToNow, parseISO } from 'date-fns';

export const fmtDate = (iso: string | null | undefined, fmt = 'dd MMM yyyy') => {
  if (!iso) return '—';
  try { return format(parseISO(iso), fmt); } catch { return iso; }
};

export const fmtDateTime = (iso: string | null | undefined) => {
  if (!iso) return '—';
  try { return format(parseISO(iso), 'dd MMM yyyy, hh:mm a'); } catch { return iso; }
};

export const fmtRelative = (iso: string | null | undefined) => {
  if (!iso) return '—';
  try { return formatDistanceToNow(parseISO(iso), { addSuffix: true }); } catch { return iso; }
};

export const formatDuration = (seconds: number): string => {
  if (!seconds) return '0s';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
};

export const formatINR = (amount: number | string | null | undefined): string => {
  if (amount === null || amount === undefined) return '—';
  const n = Number(amount);
  if (isNaN(n)) return '—';
  if (n >= 10_000_000) return `₹${(n / 10_000_000).toFixed(1)}Cr`;
  if (n >= 100_000)    return `₹${(n / 100_000).toFixed(1)}L`;
  if (n >= 1_000)      return `₹${(n / 1_000).toFixed(1)}K`;
  return `₹${n.toFixed(0)}`;
};

export const LEAD_STATUSES = [
  { value: 'new',           label: 'New'            },
  { value: 'attempted',     label: 'Attempted'       },
  { value: 'contacted',     label: 'Contacted'       },
  { value: 'interested',    label: 'Interested'      },
  { value: 'not_interested',label: 'Not Interested'  },
  { value: 'follow_up',     label: 'Follow-up'       },
  { value: 'negotiation',   label: 'Negotiation'     },
  { value: 'converted',     label: 'Converted / Won' },
  { value: 'lost',          label: 'Lost'            },
  { value: 'duplicate',     label: 'Duplicate'       },
];

export const LEAD_PRIORITIES = [
  { value: 'hot',    label: '🔥 Hot'   },
  { value: 'high',   label: 'High'   },
  { value: 'medium', label: 'Medium' },
  { value: 'low',    label: 'Low'    },
];

export const LEAD_SOURCES = [
  { value: 'manual',        label: 'Manual Entry'   },
  { value: 'indiamart',     label: 'IndiaMART'      },
  { value: 'meta_facebook', label: 'Meta Lead Ads'  },
  { value: 'google_ads',    label: 'Google Ads'     },
  { value: 'website',       label: 'Website'        },
  { value: 'referral',      label: 'Referral'       },
  { value: 'csv_import',    label: 'CSV Import'     },
  { value: 'webhook',       label: 'Webhook'        },
  { value: 'other',         label: 'Other'          },
];
