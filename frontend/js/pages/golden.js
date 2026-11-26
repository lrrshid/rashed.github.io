// Golden-sample trials (/golden-samples, Capabilities > Golden-sample trials): the trials of each capability model's
// reference unit, each with three attached scans: the trial, the higher-level directive letter and the official
// trial form (components/attachments.js). Statuses: the TEST list.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canChange, canEdit, lookupList, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { openModal } from '../components/modal.js';
import { card, dataTable, dl, errorBox, kpiTile, listOptions, loadingBox, refName, selectEl, statusBadge } from '../components/ui.js';
import { attachAll, canAttach, checkFiles, slotMark, slotRow } from '../components/attachments.js';
import { diff, formDialog } from './forms.js';

const SLOTS = ['GOLDEN_TRIAL', 'DIRECTIVE_LETTER', 'OFFICIAL_TRIAL_FORM'];
const FILE_KEYS = { GOLDEN_TRIAL: 'fileTrial', DIRECTIVE_LETTER: 'fileDirective', OFFICIAL_TRIAL_FORM: 'fileForm' };
const slotLabel = (slot) => t(`golden.slots.${slot}`);

export async function render(container, ctx) {
  const body = h('div');
  container.append(body);
  let model = ctx.query.model || '';
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/golden-samples', { model: model || undefined }); } catch (e) { replace(body, errorBox(e, load)); return; }
    const editable = canEdit('edit.testing');  // add a trial
    const changeable = canChange('edit.testing');  // change one
    const k = d.kpis;
    const modelSel = selectEl(listOptions(lookupList('models'), { withCode: true }), model, { includeEmpty: true, emptyLabel: t('golden.allModels') });
    modelSel.addEventListener('change', () => { model = modelSel.value; ctx.setQuery({ model: model || undefined }); load(); });
    replace(body,
      h('div', { class: 'page-head' },
        h('div', {}, h('h1', { tabindex: '-1', text: t('golden.title') }), h('div', { class: 'page-sub', text: t('golden.subtitle') })),
        h('div', { class: 'actions' }, modelSel,
          editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => trialForm(null, load) }, icon('plus'), t('golden.add')) : null)),
      h('div', { class: 'kpis' },
        ['total', 'planned', 'inProgress', 'passed', 'conditional', 'failed'].map((key) => kpiTile({ label: t(`golden.kpi.${key}`),
          value: formatCount(k[key]), tone: key === 'failed' && k[key] ? 'red' : key === 'passed' ? 'green' : undefined })),
        kpiTile({ label: t('golden.kpi.complete'), value: formatCount(k.complete), tone: 'green' }),
        kpiTile({ label: t('golden.kpi.missing'), value: formatCount(k.missing), tone: k.missing ? 'amber' : undefined })),
      h('div', { class: 'section-label' }),
      dataTable([
        { key: 'code', label: t('golden.fields.code'), render: (e) => h('button', { type: 'button', class: 'btn btn-sm btn-ghost mono', text: e.code, onclick: () => showTrial(e, load) }) },
        { key: 'title', label: t('golden.fields.title'), render: (e) => name(e, 'title') },
        { key: 'model', label: t('golden.fields.model'), render: (e) => (e.model ? h('a', { href: `/models/${e.model.id}`, text: name(e.model) }) : null) },
        { key: 'date', label: t('golden.fields.date'), render: (e) => formatDate(e.trialDate) },
        { key: 'status', label: t('fields.status'), render: (e) => statusBadge('TEST', e.status) },
        ...SLOTS.map((slot) => ({ key: slot, label: slotLabel(slot), render: (e) => slotMark(e.attachments[slot], slotLabel(slot)) })),
        { key: 'open', label: '', render: (e) => h('div', { class: 'row-actions' },
          h('button', { type: 'button', class: 'btn btn-sm', onclick: () => showTrial(e, load) }, icon('file'), t('golden.attachments')),
          changeable ? h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: () => trialForm(e, load) }, icon('edit')) : null) },
      ], d.items, { empty: t('golden.empty') }));
  }
  await load();
}

// A trial: its details and its three scans, each attachable or replaceable here.
function showTrial(trial, onChanged) {
  const body = h('div');
  const modal = openModal({ title: `${trial.code} · ${name(trial, 'title')}`, body, size: 'lg' });
  async function draw(current) {
    replace(body,
      dl([[t('golden.fields.model'), refName(current.model)], [t('golden.fields.date'), formatDate(current.trialDate)],
        [t('fields.status'), statusBadge('TEST', current.status)],
        [t('golden.fields.notes'), name(current, 'notes') === t('common.none') ? null : name(current, 'notes')]]),
      card(t('golden.attachments'), h('div', { class: 'slots' }, SLOTS.map((slot) => slotRow({
        entityType: 'GOLDEN_SAMPLE_TRIAL', entityId: current.id, docType: slot, label: slotLabel(slot), current: current.attachments[slot],
        onChanged: async () => {
          onChanged();
          const d = await api.get('/golden-samples');
          const fresh = d.items.find((x) => x.id === current.id);
          if (fresh) draw(fresh);
        },
      })))));
  }
  draw(trial);
  return modal;
}

async function trialForm(trial, onSaved) {
  const code = trial ? trial.code : (await api.get('/golden-samples/next-code')).code;
  const statusOptions = statuses('TEST').filter((s) => !s.archived).map((s) => ({ value: s.code, label: name(s) }));
  const spec = [
    { key: 'code', label: t('golden.fields.code'), required: true, readonly: true, dir: 'ltr' },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions },
    { key: 'titleEn', label: t('golden.fields.titleEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'titleAr', label: t('golden.fields.titleAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'modelId', label: t('golden.fields.model'), type: 'select', required: true, options: listOptions(lookupList('models'), { withCode: true }) },
    { key: 'trialDate', label: t('golden.fields.date'), type: 'date', required: true },
    { key: 'notesEn', label: t('golden.fields.notesEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    { key: 'notesAr', label: t('golden.fields.notesAr'), type: 'textarea', dir: 'rtl', max: 2000 },
    ...(canAttach() ? SLOTS.map((slot) => ({ key: FILE_KEYS[slot], label: slotLabel(slot), type: 'file', current: trial && trial.attachments[slot] })) : []),
  ];
  const values = trial ? { code, statusCode: trial.status, titleEn: trial.titleEn, titleAr: trial.titleAr, modelId: trial.model && trial.model.id,
    trialDate: trial.trialDate, notesEn: trial.notesEn, notesAr: trial.notesAr } : { code, statusCode: 'PLANNED' };
  formDialog({
    title: trial ? t('golden.editTitle', { code }) : t('golden.newTitle'), spec, values, withReason: Boolean(trial),
    submit: async (data) => {
      const files = Object.fromEntries(SLOTS.map((slot) => [slot, data[FILE_KEYS[slot]]]));
      for (const key of Object.values(FILE_KEYS)) delete data[key];
      checkFiles(files);
      const saved = trial ? await api.patch(`/golden-samples/${trial.id}`, { ...diff(values, data), version: trial.version })
        : await api.post('/golden-samples', { ...data, code });
      await attachAll('GOLDEN_SAMPLE_TRIAL', saved.id, files);
      return saved;
    },
    onSaved,
  });
}

