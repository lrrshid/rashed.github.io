// Scans in a record's fixed slots (golden-sample trials, maintenance orders, tests; document_service.SLOTS on the
// server). POST /attachments: a slot's first scan makes its document, every later scan is a new version of it, so
// nothing is lost. Opening a file uses the document's normal (permission-checked) download address.
import { request } from '../api.js';
import { h, icon } from '../lib/dom.js';
import { canChange, canEdit } from '../lib/state.js';
import { t } from '../labels.js';
import { badge, toast } from './ui.js';

export const MAX_BYTES = 20 * 1024 * 1024;
export const ACCEPT = '.pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx';
export const fileUrl = (documentId) => `/api/v1/documents/${documentId}/file`;
// A slot's first scan is adding; replacing it is a change, which needs records.change (lib/state.js canChange).
export const canAttach = () => canEdit('edit.documents');
export const canReplace = () => canChange('edit.documents');

export function attachScan(entityType, entityId, docType, file) {
  if (file.size > MAX_BYTES) return Promise.reject(new Error(t('documents.tooBig')));
  const form = new FormData();
  form.append('entityType', entityType);
  form.append('entityId', entityId);
  form.append('docType', docType);
  form.append('file', file, file.name);
  return request('POST', '/attachments', { form });
}

// Files chosen in a form, too large ones refused before anything is saved.
export function checkFiles(files) {
  for (const file of Object.values(files)) {
    if (file && file.size > MAX_BYTES) throw new Error(`${file.name}: ${t('documents.tooBig')}`);
  }
}

// After a record was saved from a form: each chosen file into its slot. The record is saved either way; a file that
// was refused is named in a message so it can be attached again.
export async function attachAll(entityType, entityId, files) {
  const problems = [];
  for (const [docType, file] of Object.entries(files)) {
    if (!file) continue;
    try { await attachScan(entityType, entityId, docType, file); } catch (e) { problems.push(`${file.name}: ${e.message}`); }
  }
  if (problems.length) toast(t('attachments.partly', { list: problems.join(' · ') }), true);
  return problems;
}

// The current file of a slot as a link, or "not attached".
export function currentFile(current) {
  return current
    ? h('a', { class: 'slot-file', href: fileUrl(current.id), target: '_blank', rel: 'noopener' }, icon('file'),
      h('span', { text: current.fileName }), h('span', { class: 'muted small', text: ` · v${current.version}` }))
    : h('span', { class: 'muted small', text: t('attachments.none') });
}

// A compact mark for a table cell: the slot holds a file (open it) or not.
export function slotMark(current, label) {
  return current
    ? h('a', { href: fileUrl(current.id), target: '_blank', rel: 'noopener', title: `${label}: ${current.fileName}` },
      badge('green', t('attachments.attached')))
    : badge('grey', t('attachments.missing'), 'no-dot');
}

// One slot with its label, its current file and (for people who may attach documents) a button to add a scan.
export function slotRow({ entityType, entityId, docType, label, current, onChanged }) {
  const input = h('input', { type: 'file', accept: ACCEPT, class: 'slot-input', 'aria-label': label });
  const button = h('button', { type: 'button', class: 'btn btn-sm' }, icon(current ? 'restore' : 'plus'),
    t(current ? 'attachments.replace' : 'attachments.add'));
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    button.disabled = true;
    try {
      await attachScan(entityType, entityId, docType, file);
      toast(t('attachments.saved'));
      if (onChanged) onChanged();
    } catch (e) { toast(e.message, true); } finally { button.disabled = false; input.value = ''; }
  });
  return h('div', { class: 'slot' },
    h('div', { class: 'slot-label', text: label }),
    h('div', { class: 'slot-current' }, currentFile(current)),
    (current ? canReplace() : canAttach()) ? h('div', { class: 'slot-action' }, input, button) : null);
}
