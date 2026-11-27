import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { leadsApi } from '../api';
import { Modal, Input, Select, Textarea, Spinner, useToast, EmptyState, ConfirmDialog } from '../components/ui';
import { getErrorMessage } from '../utils/errors';
import type { CustomField } from '../types';

// Settings → Custom Fields. Admins add, edit, switch off and delete the extra
// boxes on the Add Lead form (also the columns an import can map onto);
// everyone else sees the list.

const FIELD_TYPES: Array<{ value: string; label: string }> = [
  { value: 'text', label: 'Short text' },
  { value: 'textarea', label: 'Long text' },
  { value: 'number', label: 'Number' },
  { value: 'date', label: 'Date' },
  { value: 'dropdown', label: 'Dropdown (pick one)' },
  { value: 'checkbox', label: 'Checkbox (Yes/No)' },
  { value: 'phone', label: 'Phone number' },
  { value: 'url', label: 'Website link' },
];
const typeLabel = (t: string) => FIELD_TYPES.find(x => x.value === t)?.label ?? t;

type FieldForm = {
  id?: number; name: string; field_key?: string; field_type: string; is_required: boolean;
  is_active: boolean; sort_order: string; options: string; placeholder: string;
};
const blankField = (sortOrder: number): FieldForm => ({
  name: '', field_type: 'text', is_required: false, is_active: true,
  sort_order: String(sortOrder), options: '', placeholder: '',
});

export default function CustomFieldsPanel({ canEdit }: { canEdit: boolean }) {
  const { showToast } = useToast();
  const qc = useQueryClient();
  const [form, setForm] = useState<FieldForm | null>(null);
  const [toDelete, setToDelete] = useState<CustomField | null>(null);

  const q = useQuery({
    queryKey: ['custom-fields', 'settings', canEdit],
    queryFn: () => leadsApi.listCustomFields(canEdit ? { include_inactive: true } : undefined).then(r => r.data),
  });
  const fields = q.data ?? [];

  // The lead form, lead detail, import mapping and the integrations all read
  // ['custom-fields'], so every write refreshes them too.
  const refresh = () => qc.invalidateQueries({ queryKey: ['custom-fields'] });

  const save = useMutation({
    mutationFn: () => {
      const f = form!;
      const payload = {
        name: f.name.trim(),
        is_required: f.is_required,
        is_active: f.is_active,
        sort_order: Number(f.sort_order) || 0,
        placeholder: f.placeholder.trim(),
        options: f.field_type === 'dropdown'
          ? f.options.split('\n').map(o => o.trim()).filter(Boolean)
          : [],
      };
      return f.id
        ? leadsApi.updateCustomField(f.id, payload)
        : leadsApi.createCustomField({ ...payload, field_type: f.field_type });
    },
    onSuccess: () => {
      const edited = !!form?.id;
      refresh();
      setForm(null);
      showToast('success', edited ? 'Field updated' : 'Field added',
        edited ? '' : 'It now shows on the Add Lead form and in import mapping.');
    },
    onError: (e: unknown) => showToast('error', 'Not saved', getErrorMessage(e, 'Please check the field and try again.')),
  });

  const toggle = useMutation({
    mutationFn: (f: CustomField) => leadsApi.updateCustomField(f.id, { is_active: !f.is_active }),
    onSuccess: (_r, f) => {
      refresh();
      showToast('success', f.is_active ? 'Field switched off' : 'Field switched on',
        f.is_active ? 'Hidden from forms. Values already saved on leads are kept.' : '');
    },
    onError: (e: unknown) => showToast('error', 'Could not change it', getErrorMessage(e, 'Please try again.')),
  });

  const remove = useMutation({
    mutationFn: (f: CustomField) => leadsApi.deleteCustomField(f.id),
    onSuccess: () => { refresh(); setToDelete(null); showToast('success', 'Field deleted', ''); },
    onError: (e: unknown) => { setToDelete(null); showToast('error', 'Could not delete', getErrorMessage(e, 'Please try again.')); },
  });

  const openEdit = (f: CustomField) => setForm({
    id: f.id, name: f.name, field_key: f.field_key, field_type: f.field_type, is_required: f.is_required,
    is_active: f.is_active, sort_order: String(f.sort_order ?? 0),
    options: (f.options ?? []).join('\n'), placeholder: f.placeholder ?? '',
  });

  const nextOrder = fields.length ? Math.max(...fields.map(f => f.sort_order ?? 0)) + 1 : 0;
  const optionCount = form ? form.options.split('\n').filter(o => o.trim()).length : 0;
  const canSave = !!form && !!form.name.trim() && (form.field_type !== 'dropdown' || optionCount > 0);

  const linkBtn = (color: string) => ({
    background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '0.78rem', color,
  });

  return (
    <div>
      <div className="card p-3 mb-3 flex items-center justify-between gap-3 flex-wrap"
           style={{ fontSize: '0.82rem', color: 'var(--text-2)' }}>
        <span>
          Extra details you want on every lead — property type, budget, project name. They show on the
          Add Lead form, on the lead's page and in the app, and an import can fill them from a spreadsheet column.
          {!canEdit && ' Only an admin can change them.'}
        </span>
        {canEdit && (
          <button onClick={() => setForm(blankField(nextOrder))}
                  className="btn-brutal btn-primary px-3 py-1.5 font-heading font-black"
                  style={{ fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
            + Add field
          </button>
        )}
      </div>

      {q.isLoading ? <Spinner /> : fields.length === 0 ? (
        <EmptyState icon="☰" title="No custom fields yet"
                    message={canEdit
                      ? 'Add the extra details your team needs to capture on each lead.'
                      : 'Ask an admin to add the extra details your team needs on each lead.'} />
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table className="table-brutal">
            <thead><tr>
              {['Field name', 'Key', 'Type', 'Required', 'Order', 'Status', ...(canEdit ? [''] : [])]
                .map((h, i) => <th key={h || `actions-${i}`}>{h}</th>)}
            </tr></thead>
            <tbody>
              {fields.map(f => (
                <tr key={f.id} style={f.is_active ? undefined : { opacity: 0.6 }}>
                  <td className="font-heading font-bold" style={{ fontSize: '0.83rem' }}>
                    {f.name}
                    {f.field_type === 'dropdown' && f.options?.length > 0 && (
                      <div style={{ fontSize: '0.7rem', fontWeight: 500, color: 'var(--text-3)' }}>
                        {f.options.slice(0, 4).join(' · ')}{f.options.length > 4 ? ` +${f.options.length - 4}` : ''}
                      </div>
                    )}
                  </td>
                  <td className="font-mono" style={{ fontSize: '0.75rem', color: 'var(--text-2)' }}>{f.field_key}</td>
                  <td><span className="tag">{typeLabel(f.field_type)}</span></td>
                  <td>{f.is_required ? <span className="badge status-active">Required</span> : <span style={{ color: 'var(--line-2)', fontSize: '0.8rem' }}>Optional</span>}</td>
                  <td style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>{f.sort_order}</td>
                  <td>{f.is_active ? <span className="badge status-active">Active</span> : <span className="badge status-inactive">Switched off</span>}</td>
                  {canEdit && (
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <button onClick={() => openEdit(f)} className="font-heading font-bold px-2 py-1" style={linkBtn('var(--brass)')}>Edit</button>
                      <button onClick={() => toggle.mutate(f)} disabled={toggle.isPending}
                              className="font-heading font-bold px-2 py-1" style={linkBtn('var(--text-2)')}>
                        {f.is_active ? 'Switch off' : 'Switch on'}
                      </button>
                      <button onClick={() => setToDelete(f)} className="font-heading font-bold px-2 py-1" style={linkBtn('var(--hot)')}>Delete</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {form && (
        <Modal title={form.id ? 'Edit field' : 'New custom field'} onClose={() => setForm(null)}>
          <div className="flex flex-col gap-3">
            <Input label="Field name *" value={form.name} autoFocus maxLength={100}
                   onChange={e => setForm(p => p && ({ ...p, name: e.target.value }))}
                   placeholder="e.g. Budget, Property type, Project"
                   hint={form.id ? `Key: ${form.field_key} (used by imports and the API; it doesn't change)` : 'What your team sees on the lead form.'} />
            <Select label="Type" value={form.field_type} disabled={!!form.id}
                    onChange={e => setForm(p => p && ({ ...p, field_type: e.target.value }))}
                    hint={form.id ? "A field's type can't change once it exists. Switch it off and add a new one instead." : undefined}>
              {FIELD_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </Select>
            {form.field_type === 'dropdown' && (
              <Textarea label="Options *" rows={5} value={form.options}
                        onChange={e => setForm(p => p && ({ ...p, options: e.target.value }))}
                        placeholder={'Flat\nVilla\nPlot'}
                        hint="One option per line." />
            )}
            {form.field_type !== 'checkbox' && form.field_type !== 'dropdown' && (
              <Input label="Placeholder" value={form.placeholder} maxLength={200}
                     onChange={e => setForm(p => p && ({ ...p, placeholder: e.target.value }))}
                     placeholder="Hint shown inside the empty box" />
            )}
            <Input label="Order" type="number" min={0} value={form.sort_order}
                   onChange={e => setForm(p => p && ({ ...p, sort_order: e.target.value }))}
                   hint="Where it sits on the form. Lower shows first." />
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.is_required}
                     onChange={e => setForm(p => p && ({ ...p, is_required: e.target.checked }))}
                     style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Required (a lead can't be saved without it)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.is_active}
                     onChange={e => setForm(p => p && ({ ...p, is_active: e.target.checked }))}
                     style={{ width: '16px', height: '16px' }} />
              <span className="font-medium" style={{ fontSize: '0.82rem' }}>Active (shown on forms)</span>
            </label>
          </div>
          <div className="flex gap-3 mt-4">
            <button onClick={() => setForm(null)} className="btn-brutal btn-secondary flex-1 py-2.5 font-heading font-black">Cancel</button>
            <button onClick={() => save.mutate()} disabled={save.isPending || !canSave}
                    className="btn-brutal btn-primary flex-1 py-2.5 font-heading font-black" style={{ boxShadow: 'var(--shadow)' }}>
              {save.isPending ? '◌ Saving…' : form.id ? 'Save changes →' : 'Add field →'}
            </button>
          </div>
        </Modal>
      )}

      {toDelete && (
        <ConfirmDialog
          title={`Delete "${toDelete.name}"?`}
          message="This also deletes the value saved in this field on every lead, and can't be undone. To just hide it from forms and keep the values, use Switch off instead."
          confirmLabel={remove.isPending ? 'Deleting…' : 'Delete'}
          danger
          onConfirm={() => remove.mutate(toDelete)}
          onCancel={() => setToDelete(null)}
        />
      )}
    </div>
  );
}
