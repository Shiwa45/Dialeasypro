import { useState, useRef } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { leadsApi } from '../api';
import { SectionHeader, useToast, Spinner } from '../components/ui';
import { fmtDateTime } from '../utils/fmt';
import type { LeadImportJob } from '../types';

export default function LeadImport() {
  const { showToast } = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [options, setOptions] = useState({ duplicate_action: 'skip', source: 'csv_import' });
  const [jobId, setJobId] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data: jobStatus, isLoading: jobLoading } = useQuery({
    queryKey: ['import-job', jobId],
    queryFn: () => leadsApi.getImportJob(jobId!).then(r => r.data as LeadImportJob),
    enabled: !!jobId,
    refetchInterval: 3000,
  });

  const importMut = useMutation({
    mutationFn: () => leadsApi.importLeads(file!, options),
    onSuccess: res => {
      setJobId(res.data.import_job_id);
      setFile(null);
      showToast('success', 'Import started!', 'Track progress below.');
    },
    onError: () => showToast('error', 'Upload failed', 'Check file format (CSV or XLSX) and try again.'),
  });

  const job = jobStatus as LeadImportJob | undefined;
  const STATUS_BG: Record<string, string> = {
    processing: '#fef9c3', completed: '#dcfce7', partial: '#fef3c7',
    failed: '#fee2e2', pending: '#f3f4f6',
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith('.csv') || f.name.endsWith('.xlsx'))) {
      setFile(f);
    } else {
      showToast('error', 'Invalid file', 'Only CSV and XLSX files are supported.');
    }
  };

  return (
    <div className="p-6 flex flex-col gap-5" style={{ background: '#f5f4f0', minHeight: '100%' }}>
      <SectionHeader title="Import Leads" sub="Bulk-upload leads from CSV or Excel (XLSX)" />

      <div style={{ maxWidth: '580px' }}>
        <div className="card p-5 flex flex-col gap-4">
          {/* Drop zone */}
          <div
            onClick={() => fileRef.current?.click()}
            onDragOver={e => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            style={{
              border: `3px dashed ${dragging ? '#ffe17c' : '#000'}`,
              padding: '40px 20px',
              textAlign: 'center',
              cursor: 'pointer',
              background: file ? '#fffbee' : dragging ? '#fffff0' : '#f9f9f9',
              transition: 'all 0.15s ease',
            }}
          >
            <input ref={fileRef} type="file" accept=".csv,.xlsx" style={{ display: 'none' }}
                   onChange={e => e.target.files?.[0] && setFile(e.target.files[0])} />
            <div style={{ fontSize: '2.5rem', marginBottom: '10px', opacity: file ? 1 : 0.4 }}>
              {file ? '✓' : '↑'}
            </div>
            <div className="font-heading font-black" style={{ fontSize: '0.95rem', marginBottom: '4px' }}>
              {file ? file.name : 'Drop your CSV or XLSX file here'}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#888' }}>
              {file ? `${(file.size / 1024).toFixed(1)} KB · Click to change` : 'or click to browse · CSV / XLSX supported'}
            </div>
          </div>

          {/* Options */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Duplicate Action</label>
              <select value={options.duplicate_action} onChange={e => setOptions(p => ({ ...p, duplicate_action: e.target.value }))} className="input-brutal" style={{ cursor: 'pointer' }}>
                <option value="skip">Skip duplicates</option>
                <option value="update">Update existing lead</option>
                <option value="create_new">Allow duplicates</option>
              </select>
            </div>
            <div>
              <label className="block font-heading font-bold mb-1" style={{ fontSize: '0.72rem', textTransform: 'uppercase' }}>Default Source</label>
              <select value={options.source} onChange={e => setOptions(p => ({ ...p, source: e.target.value }))} className="input-brutal" style={{ cursor: 'pointer' }}>
                <option value="csv_import">CSV Import</option>
                <option value="indiamart">IndiaMART</option>
                <option value="manual">Manual</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>

          {/* Column guide */}
          <div style={{ background: '#fffbee', border: '2px solid #ffe17c', padding: '10px 12px', fontSize: '0.75rem', lineHeight: 1.6 }}>
            <strong>Required columns:</strong> <code className="font-mono">name</code>, <code className="font-mono">phone</code><br />
            <strong>Optional:</strong> <code className="font-mono">email</code>, <code className="font-mono">city</code>, <code className="font-mono">state</code>, <code className="font-mono">requirement</code>, <code className="font-mono">budget</code><br />
            Column names are auto-detected from common variants. Max 50,000 rows per file.
          </div>

          <button
            onClick={() => importMut.mutate()}
            disabled={!file || importMut.isPending}
            className="btn-brutal btn-primary w-full py-3 font-heading font-black"
            style={{ fontSize: '0.9rem', boxShadow: '5px 5px 0 #000' }}
          >
            {importMut.isPending ? '◌ Uploading…' : '↑ Start Import →'}
          </button>
        </div>

        {/* Job status card */}
        {job && (
          <div className="card p-4 mt-4" style={{ background: STATUS_BG[job.status] ?? '#fff' }}>
            <div className="flex items-center justify-between mb-3">
              <div className="font-heading font-black" style={{ fontSize: '0.9rem' }}>{job.original_filename}</div>
              <span className="badge" style={{ background: STATUS_BG[job.status] ?? '#e5e5e5', borderColor: '#000' }}>
                {job.status.toUpperCase()}
              </span>
            </div>
            <div className="progress-bar mb-3">
              <div className="progress-fill" style={{ width: `${job.progress_percent}%` }} />
            </div>
            <div className="grid grid-cols-3 gap-3 text-center mb-3">
              <div>
                <div className="font-heading font-black" style={{ fontSize: '1.4rem', color: '#22c55e' }}>{job.successful_rows}</div>
                <div style={{ fontSize: '0.7rem', color: '#555' }}>Successful</div>
              </div>
              <div>
                <div className="font-heading font-black" style={{ fontSize: '1.4rem', color: '#ef4444' }}>{job.failed_rows}</div>
                <div style={{ fontSize: '0.7rem', color: '#555' }}>Failed</div>
              </div>
              <div>
                <div className="font-heading font-black" style={{ fontSize: '1.4rem', color: '#888' }}>{job.duplicate_rows}</div>
                <div style={{ fontSize: '0.7rem', color: '#555' }}>Duplicates</div>
              </div>
            </div>
            <div style={{ fontSize: '0.72rem', color: '#888', textAlign: 'center' }}>
              {job.processed_rows} / {job.total_rows} rows processed · {job.progress_percent}%
            </div>
            {job.completed_at && (
              <div style={{ fontSize: '0.72rem', color: '#888', textAlign: 'center', marginTop: '4px' }}>
                Completed: {fmtDateTime(job.completed_at)}
              </div>
            )}
            {job.status === 'completed' || job.status === 'partial' ? (
              <div style={{ marginTop: '12px', textAlign: 'center' }}>
                <a href="/leads" className="btn-brutal btn-primary px-4 py-2 font-heading font-black" style={{ fontSize: '0.82rem', display: 'inline-block', textDecoration: 'none' }}>
                  View Imported Leads →
                </a>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
