// Document management: versioned documents linked to records; upload a new version, open or download any version.
import { api, request } from '../api.js';
import { debounce, h, icon, replace } from '../lib/dom.js';
import { canChange, canEdit } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatDate, formatDateTime, formatNumber } from '../lib/format.js';
import { openModal } from '../components/modal.js';
import { card, dataTable, errorBox, field, loadingBox, selectEl, toast } from '../components/ui.js';
import { formDialog } from './forms.js';

const size = (bytes) => (bytes >= 1048576 ? `${formatNumber(bytes / 1048576, 1)} MB` : `${formatNumber(bytes / 1024, 0)} KB`);
const fileUrl = (doc, version) => `/api/v1/documents/${doc.id}/file${version ? `?version=${version}` : ''}`;
// Kinds kept in the culture library (pages/culture.js); the server refuses them anywhere else.
const LIBRARY_TYPES = ['REFERENCE', 'USER_GUIDE', 'ACQUISITION_PLAN'];

export async function render(container, ctx) {
  const filters = { q: ctx.query.q || '', type: ctx.query.type || '', entityType: ctx.query.entityType || '' };
  const list = h('div');
  const editable = canEdit('edit.documents');
  const search = h('input', { class: 'input', type: 'search', value: filters.q, placeholder: t('common.search') });
  search.addEventListener('input', debounce(() => { filters.q = search.value.trim(); save(); load(); }, 300));
  const typeSel = selectEl(Object.keys(t('documents.types')).map((k) => ({ value: k, label: t(`documents.types.${k}`) })), filters.type, { includeEmpty: true });
  typeSel.addEventListener('change', () => { filters.type = typeSel.value; save(); load(); });
  const entSel = selectEl(Object.keys(t('documents.entities')).map((k) => ({ value: k, label: t(`documents.entities.${k}`) })), filters.entityType, { includeEmpty: true });
  entSel.addEventListener('change', () => { filters.entityType = entSel.value; save(); load(); });
  const save = () => ctx.setQuery(filters);
  container.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: t('documents.title') }), h('div', { class: 'page-sub', text: t('documents.subtitle') })),
      editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => newDocument(load) }, icon('plus'), t('documents.add')) : null),
    h('div', { class: 'filters' }, h('div', { class: 'field search' }, h('label', { text: t('common.search') }), search),
      field(t('documents.fields.type'), typeSel), field(t('documents.fields.linkedType'), entSel)),
    list);

  async function load() {
    replace(list, loadingBox());
    try {
      const d = await api.get('/documents', { q: filters.q || undefined, type: filters.type || undefined, entityType: filters.entityType || undefined });
      replace(list, dataTable([
        { key: 'code', label: t('documents.fields.code'), render: (doc) => h('button', { type: 'button', class: 'btn btn-sm btn-ghost mono', text: doc.code, onclick: () => showDocument(doc.id, load) }) },
        { key: 'title', label: t('documents.fields.title'), render: (doc) => name(doc, 'title') },
        { key: 'type', label: t('documents.fields.type'), render: (doc) => t(`documents.types.${doc.docType}`) },
        { key: 'linked', label: t('documents.fields.linked'), render: (doc) => h('a', { href: doc.linked.link, text: `${t(`documents.entities.${doc.linked.type}`)} · ${doc.linked.code}` }) },
        { key: 'version', label: t('documents.fields.version'), num: true, render: (doc) => String(doc.currentVersion) },
        { key: 'date', label: t('documents.fields.date'), render: (doc) => (doc.latest ? formatDate(doc.latest.uploadedAt.slice(0, 10)) : null) },
        { key: 'by', label: t('documents.fields.by'), render: (doc) => (doc.latest ? doc.latest.uploadedBy : null) },
        { key: 'open', label: '', render: (doc) => (doc.latest ? h('a', { class: 'btn btn-sm', href: fileUrl(doc), target: '_blank', rel: 'noopener' }, icon('download'), t('documents.open')) : null) },
      ], d.items));
    } catch (e) { replace(list, errorBox(e, load)); }
  }
  await load();
}

async function newDocument(onSaved) {
  const [{ code }, projects, models] = await Promise.all([api.get('/documents/next-code'), api.get('/projects'), api.get('/models')]);
  const records = [...projects.items.map((p) => ({ value: `PROJECT:${p.id}`, label: `${t('documents.entities.PROJECT')} · ${p.code} · ${name(p)}` })),
    ...models.items.map((m) => ({ value: `CAPABILITY_MODEL:${m.id}`, label: `${t('documents.entities.CAPABILITY_MODEL')} · ${m.code} · ${name(m)}` }))];
  formDialog({
    title: t('documents.newTitle'), size: 'md', values: { code, docType: 'REPORT' },
    spec: [
      { key: 'code', label: t('documents.fields.code'), required: true, readonly: true, dir: 'ltr' },
      { key: 'docType', label: t('documents.fields.type'), type: 'select', required: true, options: Object.keys(t('documents.types'))
        .filter((k) => !LIBRARY_TYPES.includes(k)).map((k) => ({ value: k, label: t(`documents.types.${k}`) })) },
      { key: 'titleEn', label: t('documents.fields.titleEn'), required: true, max: 200, dir: 'ltr', span: true },
      { key: 'titleAr', label: t('documents.fields.titleAr'), required: true, max: 200, dir: 'rtl', span: true },
      { key: 'record', label: t('documents.fields.linkedRecord'), type: 'select', required: true, options: records, span: true },
    ],
    submit: (data) => {
      const [entityType, entityId] = (data.record || ':').split(':');
      return api.post('/documents', { code, docType: data.docType, titleEn: data.titleEn, titleAr: data.titleAr, entityType, entityId });
    },
    onSaved: (doc) => { onSaved(); showDocument(doc.id, onSaved); },
  });
}

async function showDocument(id, onChanged) {
  const body = h('div', {}, loadingBox());
  const modal = openModal({ title: t('documents.title'), body, size: 'lg' });
  async function load() {
    const doc = await api.get(`/documents/${id}`);
    const fileInput = h('input', { type: 'file', class: 'input', accept: '.pdf,.png,.jpg,.jpeg,.docx,.xlsx,.pptx,.txt,.csv' });
    const note = h('input', { class: 'input', maxlength: 500 });
    const uploadBtn = h('button', { type: 'button', class: 'btn btn-primary' }, icon('plus'), t('documents.upload'));
    uploadBtn.addEventListener('click', async () => {
      const file = fileInput.files[0];
      if (!file) return;
      if (file.size > 20 * 1024 * 1024) { toast(t('documents.tooBig'), true); return; }
      const form = new FormData();
      form.append('file', file, file.name);
      if (note.value.trim()) form.append('note', note.value.trim());
      uploadBtn.disabled = true;
      try { await request('POST', `/documents/${id}/versions`, { form }); toast(t('common.saved')); onChanged(); await load(); } catch (e) { toast(e.message, true); } finally { uploadBtn.disabled = false; }
    });
    replace(body,
      h('h3', { text: `${doc.code} · ${name(doc, 'title')}` }),
      h('p', { class: 'muted small' }, `${t(`documents.types.${doc.docType}`)} · `, h('a', { href: doc.linked.link, text: `${t(`documents.entities.${doc.linked.type}`)} ${doc.linked.code} · ${name(doc.linked)}` })),
      // The first file completes a new document (adding); a later one replaces it, a change (records.change).
      (doc.currentVersion ? canChange('edit.documents') : canEdit('edit.documents')) ? card(t('documents.upload'), h('div', { class: 'form-grid' }, field(t('documents.file'), fileInput), field(t('documents.note'), note),
        h('div', { class: 'field' }, h('span', { class: 'label', text: ' ' }), uploadBtn))) : null,
      h('div', { class: 'section-label', text: t('documents.versions') }),
      dataTable([
        { key: 'v', label: t('documents.fields.version'), num: true, render: (v) => String(v.versionNo) },
        { key: 'f', label: t('documents.fields.fileName'), render: (v) => v.fileName },
        { key: 'n', label: t('documents.note'), render: (v) => v.note },
        { key: 's', label: t('documents.fields.size'), num: true, render: (v) => size(v.sizeBytes) },
        { key: 'd', label: t('documents.fields.date'), render: (v) => formatDateTime(v.uploadedAt) },
        { key: 'b', label: t('documents.fields.by'), render: (v) => v.uploadedBy },
        { key: 'o', label: '', render: (v) => h('a', { class: 'btn btn-sm', href: fileUrl(doc, v.versionNo), target: '_blank', rel: 'noopener' }, icon('download'), t('documents.open')) },
      ], doc.versions));
  }
  try { await load(); } catch (e) { replace(body, errorBox(e)); }
  return modal;
}
