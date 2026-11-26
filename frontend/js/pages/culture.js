// Culture (/culture/references, /culture/guide, /culture/acquisition): three libraries of scanned documents, the
// references, the user guides and the acquisition plans. Each scan is a versioned document of the culture library
// (entity LIBRARY on the server), seen by everyone; adding one needs the "edit documents" permission.
import { api, request } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { name, t } from '../labels.js';
import { formatDate } from '../lib/format.js';
import { dataTable, errorBox, loadingBox, toast } from '../components/ui.js';
import { ACCEPT, MAX_BYTES, canAttach, canReplace, currentFile } from '../components/attachments.js';
import { formDialog } from './forms.js';

const PAGES = {
  '/culture/references': { key: 'references', docType: 'REFERENCE' },
  '/culture/guide': { key: 'guide', docType: 'USER_GUIDE' },
  '/culture/acquisition': { key: 'acquisition', docType: 'ACQUISITION_PLAN' },
};
const LIBRARY_ID = '1';

export async function render(container) {
  const page = PAGES[window.location.pathname] || PAGES['/culture/references'];
  const body = h('div');
  container.append(body);
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/documents', { entityType: 'LIBRARY', type: page.docType }); } catch (e) { replace(body, errorBox(e, load)); return; }
    replace(body,
      h('div', { class: 'page-head' },
        h('div', {}, h('div', { class: 'page-kicker', text: t('culture.title') }), h('h1', { tabindex: '-1', text: t(`culture.${page.key}.title`) }),
          h('div', { class: 'page-sub', text: t(`culture.${page.key}.subtitle`) })),
        canAttach() ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => addScan(page, load) }, icon('plus'), t('culture.add')) : null),
      dataTable([
        { key: 'title', label: t('culture.fields.title'), render: (doc) => name(doc, 'title') },
        { key: 'file', label: t('culture.fields.file'), render: (doc) => currentFile(doc.latest ? { id: doc.id, fileName: doc.latest.fileName, version: doc.currentVersion } : null) },
        { key: 'date', label: t('culture.fields.date'), render: (doc) => (doc.latest ? formatDate(doc.latest.uploadedAt.slice(0, 10)) : null) },
        { key: 'by', label: t('culture.fields.by'), render: (doc) => (doc.latest ? doc.latest.uploadedBy : null) },
        { key: 'code', label: t('culture.fields.code'), render: (doc) => h('span', { class: 'mono small', text: doc.code }) },
        // A newer file replaces what everyone sees: a change (records.change), unless the document has no file yet.
        canAttach() ? { key: 'new', label: '', render: (doc) => ((doc.currentVersion ? canReplace() : canAttach()) ? newVersionButton(doc, load) : null) } : null,
      ].filter(Boolean), d.items, { empty: t(`culture.${page.key}.empty`) }));
  }
  await load();
}

function upload(documentId, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  return request('POST', `/documents/${documentId}/versions`, { form });
}

// A new scan: its title (in one language or both) and the file; the document and its first version are made together.
async function addScan(page, onSaved) {
  formDialog({
    title: t('culture.newTitle', { page: t(`culture.${page.key}.title`) }), size: 'md', values: {},
    spec: [
      { key: 'titleAr', label: t('culture.fields.titleAr'), max: 200, dir: 'rtl', span: true },
      { key: 'titleEn', label: t('culture.fields.titleEn'), max: 200, dir: 'ltr', span: true },
      { key: 'file', label: t('culture.fields.scan'), type: 'file', required: true, span: true },
    ],
    submit: async (data) => {
      const titleAr = data.titleAr || data.titleEn;
      const titleEn = data.titleEn || data.titleAr;
      if (!titleAr) throw new Error(t('culture.needTitle'));
      if (!data.file) throw new Error(t('culture.needFile'));
      if (data.file.size > MAX_BYTES) throw new Error(t('documents.tooBig'));
      const { code } = await api.get('/documents/next-code');
      const doc = await api.post('/documents', { code, docType: page.docType, titleEn, titleAr, entityType: 'LIBRARY', entityId: LIBRARY_ID });
      try { await upload(doc.id, data.file); } catch (e) {
        toast(t('attachments.partly', { list: `${data.file.name}: ${e.message}` }), true);
      }
      return doc;
    },
    onSaved,
  });
}

function newVersionButton(doc, onChanged) {
  const input = h('input', { type: 'file', accept: ACCEPT, class: 'slot-input', 'aria-label': t('culture.newVersion') });
  const button = h('button', { type: 'button', class: 'btn btn-sm' }, icon('restore'), t('culture.newVersion'));
  button.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    if (file.size > MAX_BYTES) { toast(t('documents.tooBig'), true); return; }
    button.disabled = true;
    try { await upload(doc.id, file); toast(t('attachments.saved')); onChanged(); } catch (e) { toast(e.message, true); } finally { button.disabled = false; }
  });
  return h('div', { class: 'slot-action' }, input, button);
}
