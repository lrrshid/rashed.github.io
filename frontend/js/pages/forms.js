// Create / edit dialogs for assets, models and requirements, built from one field description. Bilingual fields
// (English and Arabic names) side by side; the server validates everything again and its field errors are shown
// under the fields they name.
import { api } from '../api.js';
import { h } from '../lib/dom.js';
import { lookupList, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { dateField } from '../components/date-field.js';
import { openModal } from '../components/modal.js';
import { listOptions, toast } from '../components/ui.js';

// spec: [{ key, label, type: text|number|select|date|textarea|checks|bool, options, required, span, dir }]
export function formDialog({ title, spec, values = {}, submit, onSaved, size = 'lg', withReason = false }) {
  const controls = {};
  const errors = {};
  const grid = h('div', { class: 'form-grid' });
  for (const f of spec) {
    let control;
    const value = values[f.key];
    if (f.type === 'select') {
      control = h('select', { class: 'select' });
      if (!f.required) control.append(h('option', { value: '', text: t('common.none') }));
      for (const o of f.options) control.append(h('option', { value: o.value, text: o.label, selected: String(value ?? '') === String(o.value) || undefined }));
    } else if (f.type === 'textarea') {
      control = h('textarea', { class: 'input', dir: f.dir, maxlength: f.max || 4000 });
      control.value = value ?? '';
    } else if (f.type === 'date') {
      const date = dateField({ id: `fld-${f.key}`, value: value || '', label: f.label });
      control = date.node;
      control.dateInput = date.input;
    } else if (f.type === 'checks') {
      control = h('div', { class: 'checks' }, f.options.map((o) => h('label', {},
        h('input', { type: 'checkbox', value: o.value, checked: (value || []).includes(o.value) || undefined }), o.label)));
    } else if (f.type === 'bool') {
      control = h('select', { class: 'select' }, h('option', { value: '', text: t('common.none') }),
        h('option', { value: 'true', text: t('common.yes'), selected: value === true || undefined }),
        h('option', { value: 'false', text: t('common.no'), selected: value === false || undefined }));
    } else {
      control = h('input', { class: 'input', type: f.type === 'number' ? 'number' : 'text', step: f.step || (f.type === 'number' ? 'any' : undefined),
        dir: f.dir, maxlength: f.max, value: value ?? '', readonly: f.readonly || undefined });
    }
    controls[f.key] = control;
    const err = h('span', { class: 'error' });
    errors[f.key] = err;
    const id = `fld-${f.key}`;
    const input = control.querySelector && control.matches && !control.matches('input,select,textarea') ? control.querySelector('input') : control;
    if (input && f.type !== 'checks') input.id = id;
    grid.append(h('div', { class: `field ${f.span ? 'span-all' : ''}` },
      f.type === 'checks' ? h('span', { class: 'label', text: f.label + (f.required ? ' *' : '') }) : h('label', { for: id, text: f.label + (f.required ? ' *' : '') }),
      control, err));
  }
  let reason = null;
  if (withReason) {
    reason = h('input', { class: 'input', maxlength: 2000, id: 'fld-reason' });
    grid.append(h('div', { class: 'field span-all' }, h('label', { for: 'fld-reason', text: t('common.reason') }), reason));
  }
  const formError = h('div', { class: 'error-box', role: 'alert', hidden: true });
  const save = h('button', { type: 'button', class: 'btn btn-primary', text: t('common.save') });
  const cancel = h('button', { type: 'button', class: 'btn', text: t('common.cancel') });
  const modal = openModal({ title, body: h('div', {}, formError, grid), footer: [cancel, save], size });
  cancel.addEventListener('click', () => modal.close(true));

  function read() {
    const out = {};
    for (const f of spec) {
      if (f.readonly) continue;
      const c = controls[f.key];
      let v;
      if (f.type === 'checks') v = [...c.querySelectorAll('input:checked')].map((i) => i.value);
      else if (f.type === 'date') v = c.dateInput.value || (c.dateInput.dateInvalid ? 'invalid' : null);
      else if (f.type === 'bool') v = c.value === '' ? null : c.value === 'true';
      else if (f.type === 'number') v = c.value === '' ? null : Number(c.value);
      else v = c.value.trim() === '' ? null : c.value.trim();
      out[f.key] = v;
    }
    if (reason && reason.value.trim()) out.reason = reason.value.trim();
    return out;
  }

  save.addEventListener('click', async () => {
    formError.hidden = true;
    for (const e of Object.values(errors)) e.textContent = '';
    save.disabled = true;
    try {
      const result = await submit(read());
      modal.close(true);
      toast(t('common.saved'));
      if (onSaved) onSaved(result);
    } catch (error) {
      formError.textContent = error.message;
      formError.hidden = false;
      for (const fe of error.fieldErrors || []) {
        const key = fe.field.replace(/^body\./, '');
        if (errors[key]) errors[key].textContent = fe.message;
      }
    } finally {
      save.disabled = false;
    }
  });
  return modal;
}

// Only the fields that changed, plus the version (PATCH).
export function diff(before, after) {
  const out = {};
  for (const [k, v] of Object.entries(after)) {
    const old = before[k];
    const same = Array.isArray(v) ? JSON.stringify([...v].sort()) === JSON.stringify([...(old || [])].sort()) : (old ?? null) === (v ?? null);
    if (!same || k === 'reason') out[k] = v;
  }
  return out;
}

const pct = (key, label) => ({ key, label, type: 'number', step: 1 });

export function openAssetForm(asset, onSaved) {
  const models = lookupList('models').filter((m) => !m.archived || (asset && asset.model && asset.model.id === m.id));
  const spec = [
    { key: 'code', label: t('fields.assetId'), required: true, max: 30, readonly: Boolean(asset), dir: 'ltr' },
    { key: 'serialNumber', label: t('fields.serial'), max: 60, dir: 'ltr' },
    { key: 'modelId', label: t('fields.model'), type: 'select', required: true, options: models.map((m) => ({ value: m.id, label: `${m.code} · ${name(m)}` })) },
    { key: 'departmentId', label: t('fields.department'), type: 'select', required: true, options: listOptions(lookupList('departments')) },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statuses('ASSET').filter((s) => !s.archived).map((s) => ({ value: s.code, label: name(s) })) },
    { key: 'siteId', label: t('fields.site'), type: 'select', options: listOptions(lookupList('sites')) },
    pct('readinessOperational', t('fields.opReadiness')), pct('readinessTechnical', t('fields.techReadiness')),
    pct('readinessMission', t('fields.missionReadiness')), pct('readinessMaintenance', t('fields.maintReadiness')),
    { key: 'acquisitionDate', label: t('fields.acquisitionDate'), type: 'date' },
    { key: 'expectedDeliveryDate', label: t('fields.deliveryDate'), type: 'date' },
    { key: 'acquisitionMethod', label: t('fields.acquisitionMethod'), type: 'select', options: Object.keys(t('methods')).map((k) => ({ value: k, label: t(`methods.${k}`) })) },
    { key: 'contractId', label: t('fields.contract'), type: 'select', options: lookupList('contracts').map((c) => ({ value: c.id, label: `${c.code} · ${name(c)}` })) },
    { key: 'warrantyEndDate', label: t('fields.warranty'), type: 'date' },
    { key: 'unitValue', label: t('fields.unitValue'), type: 'number' },
    { key: 'serviceLifeYears', label: t('fields.serviceLife'), type: 'number', step: 1 },
    { key: 'operatingHours', label: t('fields.hours'), type: 'number', step: 1 },
    { key: 'responsibleEn', label: `${t('fields.responsible')} (EN)`, max: 160, dir: 'ltr' },
    { key: 'responsibleAr', label: `${t('fields.responsible')} (ع)`, max: 160, dir: 'rtl' },
    { key: 'notes', label: t('fields.notes'), type: 'textarea', span: true },
  ];
  const values = asset ? {
    code: asset.code, serialNumber: asset.serialNumber, modelId: asset.model && asset.model.id, departmentId: asset.department && asset.department.id,
    statusCode: asset.status, siteId: asset.site && asset.site.id, readinessOperational: asset.readiness.operational,
    readinessTechnical: asset.readiness.technical, readinessMission: asset.readiness.mission, readinessMaintenance: asset.readiness.maintenance,
    acquisitionDate: asset.acquisitionDate, expectedDeliveryDate: asset.expectedDeliveryDate, acquisitionMethod: asset.acquisitionMethod,
    contractId: asset.contract && asset.contract.id, warrantyEndDate: asset.warrantyEndDate, unitValue: asset.unitValue,
    serviceLifeYears: asset.serviceLifeYears, operatingHours: asset.operatingHours, responsibleEn: asset.responsibleEn,
    responsibleAr: asset.responsibleAr, notes: asset.notes,
  } : { statusCode: 'UNDER_ACQUISITION' };
  formDialog({
    title: asset ? t('asset.editTitle', { code: asset.code }) : t('asset.newTitle'), spec, values, withReason: Boolean(asset),
    submit: (data) => (asset ? api.patch(`/assets/${asset.id}`, { ...diff(values, data), version: asset.version }) : api.post('/assets', data)),
    onSaved,
  });
}

export function openModelForm(model, onSaved) {
  const spec = [
    { key: 'code', label: t('fields.code'), required: true, max: 20, readonly: Boolean(model), dir: 'ltr' },
    { key: 'categoryId', label: t('fields.category'), type: 'select', required: true, options: listOptions(lookupList('categories'), { withCode: true }) },
    { key: 'nameEn', label: t('fields.nameEn'), required: true, max: 160, dir: 'ltr' },
    { key: 'nameAr', label: t('fields.nameAr'), required: true, max: 160, dir: 'rtl' },
    { key: 'roleEn', label: `${t('fields.role')} (EN)`, max: 200, dir: 'ltr' },
    { key: 'roleAr', label: `${t('fields.role')} (ع)`, max: 200, dir: 'rtl' },
    { key: 'manufacturerId', label: t('fields.manufacturer'), type: 'select', options: lookupList('organizations').filter((o) => o.kind !== 'SUPPLIER').map((o) => ({ value: o.id, label: name(o) })) },
    { key: 'unitCost', label: t('fields.unitCost'), type: 'number' },
    { key: 'notes', label: t('fields.notes'), type: 'textarea', span: true },
  ];
  const values = model ? { code: model.code, categoryId: model.category && model.category.id, nameEn: model.nameEn, nameAr: model.nameAr,
    roleEn: model.roleEn, roleAr: model.roleAr, manufacturerId: model.manufacturer && model.manufacturer.id, unitCost: model.unitCost, notes: model.notes } : {};
  formDialog({
    title: model ? t('model.editTitle', { code: model.code }) : t('model.newTitle'), spec, values, withReason: Boolean(model),
    submit: (data) => (model ? api.patch(`/models/${model.id}`, { ...diff(values, data), version: model.version }) : api.post('/models', data)),
    onSaved,
  });
}

export function openSpecsForm(model, onSaved) {
  const fields = lookupList('specFields').filter((f) => !f.archived && model.category && f.categoryId === model.category.id);
  const spec = fields.map((f) => ({ key: f.code, label: `${name(f)}${f.unit ? ` (${f.unit})` : ''}`, type: f.dataType === 'NUMBER' ? 'number' : f.dataType === 'BOOL' ? 'bool' : 'text', max: 200 }));
  const values = { ...(model.specs || {}) };
  formDialog({
    title: t('model.specsEdit'), spec, values, withReason: true,
    submit: (data) => {
      const specs = {};
      for (const [k, v] of Object.entries(data)) if (k !== 'reason' && v !== null && v !== '') specs[k] = v;
      return api.patch(`/models/${model.id}`, { specs, version: model.version, reason: data.reason });
    },
    onSaved,
  });
}

export function openRequirementForm(req, onSaved) {
  const spec = [
    { key: 'code', label: t('fields.code'), required: true, max: 20, readonly: Boolean(req), dir: 'ltr' },
    { key: 'priority', label: t('fields.priority'), type: 'select', required: true, options: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((p) => ({ value: p, label: t(`priority.${p}`) })) },
    { key: 'nameEn', label: t('fields.nameEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'nameAr', label: t('fields.nameAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'departmentId', label: t('fields.department'), type: 'select', required: true, options: listOptions(lookupList('departments')) },
    { key: 'categoryId', label: t('fields.category'), type: 'select', required: true, options: listOptions(lookupList('categories'), { withCode: true }) },
    { key: 'requiredQty', label: t('fields.requiredQty'), type: 'number', step: 1, required: true },
    { key: 'targetDate', label: t('fields.targetDate'), type: 'date' },
    { key: 'modelIds', label: t('fields.models'), type: 'checks', span: true, options: lookupList('models').filter((m) => !m.archived).map((m) => ({ value: m.id, label: `${m.code} · ${name(m)}` })) },
    { key: 'notes', label: t('fields.notes'), type: 'textarea', span: true },
  ];
  const values = req ? { code: req.code, priority: req.priority, nameEn: req.nameEn, nameAr: req.nameAr, departmentId: req.department && req.department.id,
    categoryId: req.category && req.category.id, requiredQty: req.required, targetDate: req.targetDate, modelIds: (req.models || []).map((m) => m.id), notes: req.notes }
    : { priority: 'MEDIUM', modelIds: [] };
  formDialog({
    title: req ? t('requirement.editTitle', { code: req.code }) : t('requirement.newTitle'), spec, values, withReason: Boolean(req),
    submit: (data) => (req ? api.patch(`/requirements/${req.id}`, { ...diff(values, data), version: req.version }) : api.post('/requirements', data)),
    onSaved,
  });
}
