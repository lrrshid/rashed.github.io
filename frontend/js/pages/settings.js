// Settings (system administrators): configurable lists, statuses, workflows by project type, specification fields,
// AI levels, business rules, roles and permissions, users, alert rules and the audit history. No code changes needed.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { isAdmin, lookupList, setLookups, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatDateTime } from '../lib/format.js';
import { card, dataTable, errorBox, listOptions, loadingBox, pager, tabs, toast } from '../components/ui.js';
import { diff, formDialog } from './forms.js';
import { fieldLabel } from './field-labels.js';

const TABS = ['departments', 'categories', 'sites', 'organizations', 'contracts', 'statuses', 'workflows', 'specFields', 'ai',
  'rules', 'roles', 'users', 'alertRules', 'audit'];
const COLORS = ['green', 'amber', 'red', 'blue', 'purple', 'teal', 'grey', 'orange', 'pink', 'dark'];
// Business-rule keys contain dots (assets.available_statuses), so they are looked up in the rules object directly.
// Permission codes contain dots too (edit.requirements).
function permLabel(code) {
  const labels = t('settings.roles.permissions');
  return (labels && labels[code]) || code;
}
function ruleLabel(key) {
  const labels = t('settings.rules');
  return (labels && labels[key]) || key;
}
const DOMAINS = ['ASSET', 'PROJECT', 'MILESTONE', 'RISK', 'ISSUE', 'TEST', 'MAINTENANCE', 'DEVELOPMENT'];

const nameFields = [
  { key: 'nameEn', label: t('fields.nameEn'), required: true, max: 200, dir: 'ltr' },
  { key: 'nameAr', label: t('fields.nameAr'), required: true, max: 200, dir: 'rtl' },
];
const codeField = (editing) => ({ key: 'code', label: t('fields.code'), required: true, max: 30, dir: 'ltr', readonly: editing });
const sortField = { key: 'sortOrder', label: 'Order', type: 'number', step: 1 };

// Field description and table columns of each simple list.
function listSpec(kind, editing) {
  const base = [codeField(editing), ...nameFields, sortField];
  switch (kind) {
    case 'organizations': return [...base, { key: 'kind', label: 'Kind', type: 'select', required: true, options: ['MANUFACTURER', 'SUPPLIER', 'BOTH'].map((v) => ({ value: v, label: v })) },
      { key: 'countryEn', label: 'Country (EN)', max: 80 }, { key: 'countryAr', label: 'Country (ع)', max: 80, dir: 'rtl' }];
    case 'contracts': return [codeField(editing), { key: 'titleEn', label: t('fields.nameEn'), required: true, max: 200, dir: 'ltr' },
      { key: 'titleAr', label: t('fields.nameAr'), required: true, max: 200, dir: 'rtl' },
      { key: 'supplierId', label: t('fields.supplier'), type: 'select', options: listOptions(lookupList('organizations')) },
      { key: 'contractValue', label: t('fields.unitValue'), type: 'number' }, { key: 'startDate', label: 'Start', type: 'date' }, { key: 'endDate', label: 'End', type: 'date' }];
    case 'statuses': return [{ key: 'domain', label: t('settings.domain'), type: 'select', required: true, readonly: editing, options: DOMAINS.map((d) => ({ value: d, label: d })) },
      codeField(editing), ...nameFields, { key: 'color', label: t('settings.color'), type: 'select', required: true, options: COLORS.map((c) => ({ value: c, label: c })) },
      { key: 'terminal', label: t('settings.terminal'), type: 'bool' }, sortField];
    case 'specFields': return [{ key: 'categoryId', label: t('fields.category'), type: 'select', required: true, options: listOptions(lookupList('categories'), { withCode: true }) },
      { key: 'section', label: 'Section', type: 'select', required: true, options: ['PERFORMANCE', 'SENSORS', 'COMMUNICATIONS', 'ENVIRONMENT', 'OTHER'].map((s) => ({ value: s, label: t(`model.sections.${s}`) })) },
      { key: 'code', label: t('fields.code'), required: true, max: 40, dir: 'ltr', readonly: editing }, ...nameFields, { key: 'unit', label: 'Unit', max: 20 },
      { key: 'dataType', label: 'Type', type: 'select', required: true, options: ['TEXT', 'NUMBER', 'BOOL'].map((v) => ({ value: v, label: v })) }, sortField];
    default: return base;
  }
}

export async function render(container, ctx) {
  if (!isAdmin()) {
    container.append(h('div', { class: 'error-box', text: t('errors.forbidden') }));
    return;
  }
  let tab = ctx.query.tab || (window.location.pathname === '/audit' ? 'audit' : 'departments');
  const body = h('div');
  const bar = h('div');
  container.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: t('settings.title') }),
    h('div', { class: 'page-sub', text: t('settings.subtitle') }))), bar, body);
  const drawTabs = () => replace(bar, tabs(TABS.map((k) => ({ key: k, label: t(`settings.tabs.${k}`) })), tab, (k) => { tab = k; ctx.setQuery({ tab: k }); draw(); }));

  async function refreshLookups() { setLookups(await api.get('/lookups')); }

  async function draw() {
    drawTabs();
    replace(body, loadingBox());
    try {
      if (['departments', 'categories', 'sites', 'organizations', 'contracts', 'statuses', 'specFields'].includes(tab)) await simpleList(tab);
      else if (tab === 'workflows') await workflows();
      else if (tab === 'ai') await aiSettings();
      else if (tab === 'rules') await rules();
      else if (tab === 'roles') await roles();
      else if (tab === 'users') await users();
      else if (tab === 'alertRules') await alertRules();
      else await audit(0);
    } catch (e) { replace(body, errorBox(e, draw)); }
  }

  const archiveBtn = (kind, e) => h('button', { type: 'button', class: 'btn btn-sm', onclick: async () => {
    try { await api.post(`/admin/lists/${kind}/${e.id}/archive`, { archived: !e.archived, version: e.version }); await refreshLookups(); draw(); } catch (err) { toast(err.message, true); }
  } }, icon(e.archived ? 'restore' : 'archive'), e.archived ? t('common.restore') : t('common.archive'));

  function editList(kind, entry) {
    const spec = listSpec(kind, Boolean(entry));
    const values = entry ? { ...entry } : { sortOrder: 0 };
    formDialog({ title: `${t(`settings.tabs.${kind}`)}`, spec, values, size: 'md', withReason: Boolean(entry),
      submit: (data) => (entry ? api.patch(`/admin/lists/${kind}/${entry.id}`, { ...diff(values, data), version: entry.version })
        : api.post(`/admin/lists/${kind}`, data)),
      onSaved: async () => { await refreshLookups(); draw(); } });
  }

  async function simpleList(kind) {
    const d = await api.get(`/admin/lists/${kind}`);
    const cols = [
      kind === 'statuses' ? { key: 'domain', label: t('settings.domain'), render: (e) => e.domain } : null,
      kind === 'specFields' ? { key: 'cat', label: t('fields.category'), render: (e) => (lookupList('categories').find((c) => c.id === e.categoryId) || {}).code } : null,
      { key: 'code', label: t('fields.code'), render: (e) => h('span', { class: 'mono', text: e.code }) },
      { key: 'name', label: t('fields.nameEn'), render: (e) => name(e, kind === 'contracts' ? 'title' : 'name') },
      kind === 'statuses' ? { key: 'color', label: t('settings.color'), render: (e) => h('span', { class: `badge c-${e.color}`, text: e.color }) } : null,
      { key: 'state', label: t('fields.status'), render: (e) => (e.archived ? h('span', { class: 'badge c-grey', text: t('common.archived') }) : null) },
      { key: 'actions', label: '', render: (e) => h('span', { class: 'actions' }, h('button', { type: 'button', class: 'btn btn-sm', onclick: () => editList(kind, e) }, icon('edit'), t('common.edit')), archiveBtn(kind, e)) },
    ].filter(Boolean);
    replace(body, h('div', { class: 'toolbar' }, h('span', { class: 'muted small', text: t('settings.archivedShown') }),
      h('button', { type: 'button', class: 'btn btn-primary', onclick: () => editList(kind, null) }, icon('plus'), t('settings.add'))),
    dataTable(cols, d.items));
  }

  async function workflows() {
    const [types, stages] = await Promise.all([api.get('/admin/lists/projectTypes'), api.get('/admin/lists/stages')]);
    const sections = types.items.map((ty) => {
      const mine = stages.items.filter((s) => s.projectTypeId === ty.id && !s.archived).sort((a, b) => a.sortOrder - b.sortOrder);
      const move = async (index, delta) => {
        const ids = mine.map((s) => s.id);
        const [moved] = ids.splice(index, 1);
        ids.splice(index + delta, 0, moved);
        try { await api.put(`/admin/project-types/${ty.id}/stage-order`, { stageIds: [...ids, ...stages.items.filter((s) => s.projectTypeId === ty.id && s.archived).map((s) => s.id)] }); await refreshLookups(); draw(); } catch (e) { toast(e.message, true); }
      };
      return card(name(ty), h('ol', { class: 'status-list' }, mine.map((s, i) => h('li', { class: 'actions', style: 'justify-content:space-between' },
        h('span', { text: `${i + 1}. ${name(s)}` }),
        h('span', { class: 'actions' },
          h('button', { type: 'button', class: 'btn btn-sm', disabled: i === 0, 'aria-label': t('settings.moveUp'), onclick: () => move(i, -1), text: '↑' }),
          h('button', { type: 'button', class: 'btn btn-sm', disabled: i === mine.length - 1, 'aria-label': t('settings.moveDown'), onclick: () => move(i, 1), text: '↓' }),
          h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: () => formDialog({ title: name(s), size: 'md', spec: nameFields, values: s, withReason: true,
            submit: (data) => api.patch(`/admin/lists/stages/${s.id}`, { ...diff(s, data), version: s.version }), onSaved: async () => { await refreshLookups(); draw(); } }) }, icon('edit')),
          archiveBtn('stages', s))))),
      { actions: h('button', { type: 'button', class: 'btn btn-sm', onclick: () => formDialog({ title: t('settings.addStage'), size: 'md', spec: nameFields, values: {},
        submit: (data) => api.post('/admin/lists/stages', { ...data, projectTypeId: ty.id }), onSaved: async () => { await refreshLookups(); draw(); } }) }, icon('plus'), t('settings.addStage')) });
    });
    replace(body, h('div', { class: 'grid grid-2' }, sections));
  }

  async function aiSettings() {
    const d = await api.get('/ai');
    replace(body, card(t('ai.criteria'), dataTable([
      { key: 'l', label: t('ai.level'), render: (c) => `L${c.level}` },
      { key: 'n', label: t('fields.nameEn'), render: (c) => name(c) },
      { key: 'm', label: '', render: (c) => t('ai.minSupported', { n: c.minSupported }) },
      { key: 'r', label: '', render: (c) => c.required.join(', ') },
      { key: 'e', label: '', render: (c) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => formDialog({ title: `L${c.level}`, size: 'md', withReason: true,
        values: { nameEn: c.nameEn, nameAr: c.nameAr, minSupported: c.minSupported, required: c.required },
        spec: [...nameFields, { key: 'minSupported', label: t('ai.minSupported', { n: '' }), type: 'number', step: 1 },
          { key: 'required', label: t('ai.required', { list: '' }), type: 'checks', span: true, options: d.technologies.map((x) => ({ value: x.code, label: name(x) })) }],
        submit: (data) => api.patch(`/ai/levels/${c.level}`, { ...data, version: c.version }), onSaved: draw }) }, icon('edit')) },
    ], d.criteria)), h('div', { class: 'section-label' }), await (async () => { const kind = 'aiTechnologies'; const list = await api.get(`/admin/lists/${kind}`);
      return card(t('ai.matrix'), dataTable([
        { key: 'code', label: t('fields.code'), render: (e) => h('span', { class: 'mono', text: e.code }) },
        { key: 'name', label: t('fields.nameEn'), render: (e) => name(e) },
        { key: 'a', label: '', render: (e) => h('span', { class: 'actions' }, h('button', { type: 'button', class: 'btn btn-sm', onclick: () => editList(kind, e) }, icon('edit')), archiveBtn(kind, e)) },
      ], list.items), { actions: h('button', { type: 'button', class: 'btn btn-sm', onclick: () => editList(kind, null) }, icon('plus'), t('settings.add')) }); })());
  }

  async function rules() {
    const d = await api.get('/settings');
    const statusChoices = { 'assets.available_statuses': 'ASSET', 'assets.operational_statuses': 'ASSET', 'assets.pipeline_statuses': 'ASSET', 'projects.forecast_statuses': 'PROJECT' };
    replace(body, h('div', { class: 'grid grid-2' }, d.items.map((s) => {
      let spec; let values; let toValue;
      if (Array.isArray(s.value)) {
        const domain = statusChoices[s.key];
        spec = [{ key: 'codes', label: ruleLabel(s.key), type: 'checks', span: true,
          options: statuses(domain).filter((x) => !x.archived).map((x) => ({ value: x.code, label: name(x) })) }];
        values = { codes: s.value };
        toValue = (data) => data.codes;
      } else if (typeof s.value === 'object') {
        spec = Object.keys(s.value).map((k) => ({ key: k, label: ruleLabel(k), type: typeof s.default[k] === 'number' ? 'number' : 'text', dir: k === 'ar' ? 'rtl' : undefined }));
        values = { ...s.value };
        toValue = (data) => Object.fromEntries(Object.keys(s.value).map((k) => [k, data[k]]));
      } else {
        spec = [{ key: 'value', label: ruleLabel(s.key), type: 'number' }];
        values = { value: s.value };
        toValue = (data) => data.value;
      }
      const summary = Array.isArray(s.value) ? s.value.join(', ') : typeof s.value === 'object' ? Object.entries(s.value).map(([k, v]) => `${ruleLabel(k)}: ${v}`).join(' · ') : String(s.value);
      return card(ruleLabel(s.key), h('p', { class: 'small', text: summary }), { actions: h('button', { type: 'button', class: 'btn btn-sm', onclick: () => formDialog({
        title: ruleLabel(s.key), size: 'md', spec, values, withReason: true,
        submit: (data) => api.put(`/settings/${s.key}`, { value: toValue(data), version: s.version, reason: data.reason }), onSaved: draw }) }, icon('edit'), t('common.edit')) });
    })));
  }

  async function roles() {
    const d = await api.get('/admin/roles');
    const head = h('tr', {}, h('th', { text: t('settings.tabs.roles') }), d.items.map((r) => h('th', { style: 'text-align:center' }, name(r), h('div', { class: 'muted small', text: t(`settings.roles.${r.scope}`) }))));
    const rows = d.permissions.map((p) => h('tr', {}, h('th', { scope: 'row', class: 'small' }, permLabel(p), h('div', { class: 'mono muted small', text: p })),
      d.items.map((r) => {
        const box = h('input', { type: 'checkbox', checked: r.permissions.includes(p) || undefined, disabled: (r.system && p === 'admin') || undefined, 'aria-label': `${name(r)}: ${p}` });
        box.addEventListener('change', async () => {
          const perms = box.checked ? [...r.permissions, p] : r.permissions.filter((x) => x !== p);
          try { await api.patch(`/admin/roles/${r.id}`, { permissions: perms, version: r.version }); toast(t('common.saved')); draw(); } catch (e) { toast(e.message, true); draw(); }
        });
        return h('td', { style: 'text-align:center' }, box);
      })));
    replace(body, h('div', { class: 'toolbar' }, h('span'), h('button', { type: 'button', class: 'btn btn-primary', onclick: () => formDialog({ title: t('settings.roles.newRole'), size: 'md', values: { scope: 'ALL' },
      spec: [{ key: 'code', label: t('settings.roles.code'), required: true, max: 30, dir: 'ltr' }, ...nameFields,
        { key: 'scope', label: t('settings.roles.scope'), type: 'select', required: true, options: ['ALL', 'DEPARTMENT'].map((s) => ({ value: s, label: t(`settings.roles.${s}`) })) }],
      submit: (data) => api.post('/admin/roles', { ...data, permissions: ['view'] }), onSaved: async () => { await refreshLookups(); draw(); } }) }, icon('plus'), t('settings.roles.newRole'))),
    h('div', { class: 'table-wrap' }, h('table', { class: 'data' }, h('thead', {}, head), h('tbody', {}, rows))));
  }

  async function users() {
    const d = await api.get('/users', { size: 100 });
    const roleOptions = lookupList('roles').map((r) => ({ value: r.code, label: name(r) }));
    const deptOptions = listOptions(lookupList('departments'));
    const open = (u) => formDialog({ title: u ? t('settings.users.editTitle', { name: u.displayName }) : t('settings.users.newTitle'), size: 'md', withReason: Boolean(u),
      values: u ? { username: u.username, displayName: u.displayName, role: u.role, active: u.active, departmentIds: u.departments.map((x) => x.id) } : { role: 'VIEWER', departmentIds: [] },
      spec: [{ key: 'username', label: t('settings.users.username'), required: true, max: 120, dir: 'ltr', readonly: Boolean(u) },
        { key: 'displayName', label: t('settings.users.displayName'), max: 160 },
        { key: 'role', label: t('settings.users.role'), type: 'select', required: true, options: roleOptions },
        u ? { key: 'active', label: t('settings.users.active'), type: 'bool' } : { key: 'password', label: t('settings.users.password'), max: 200 },
        { key: 'departmentIds', label: t('settings.users.departments'), type: 'checks', span: true, options: deptOptions }],
      submit: (data) => (u ? api.patch(`/users/${u.id}`, { ...diff({ displayName: u.displayName, role: u.role, active: u.active, departmentIds: u.departments.map((x) => x.id) }, data), version: u.version })
        : api.post('/users', { username: data.username, displayName: data.displayName, role: data.role, password: data.password || undefined, departmentIds: data.departmentIds })),
      onSaved: draw });
    replace(body, h('div', { class: 'toolbar' }, h('span'), h('button', { type: 'button', class: 'btn btn-primary', onclick: () => open(null) }, icon('plus'), t('settings.users.add'))),
      dataTable([
        { key: 'u', label: t('settings.users.username'), render: (u) => h('span', { class: 'mono', text: u.username }) },
        { key: 'n', label: t('settings.users.displayName'), render: (u) => u.displayName },
        { key: 'r', label: t('settings.users.role'), render: (u) => name(lookupList('roles').find((r) => r.code === u.role) || { nameEn: u.role }) },
        { key: 'd', label: t('settings.users.departments'), render: (u) => u.departments.map((x) => x.code).join(', ') },
        { key: 'a', label: t('settings.users.active'), render: (u) => h('span', { class: `badge ${u.active ? 'c-green' : 'c-grey'}`, text: u.active ? t('common.yes') : t('common.no') }) },
        { key: 'e', label: '', render: (u) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => open(u) }, icon('edit')) },
      ], d.items));
  }

  async function alertRules() {
    const d = await api.get('/alert-rules');
    const roleList = lookupList('roles');
    replace(body, dataTable([
      { key: 't', label: t('documents.fields.type'), render: (r) => h('span', {}, h('span', { class: `badge c-${{ CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'amber', INFO: 'blue' }[r.severity]}`, text: t(`alerts.severity.${r.severity}`) }), ` ${t(`alerts.types.${r.type}`)}`) },
      { key: 'roles', label: t('settings.alertRules.roles'), render: (r) => r.roles.map((c) => name(roleList.find((x) => x.code === c) || { nameEn: c })).join('، ') },
      { key: 'd', label: t('settings.alertRules.daysAhead'), num: true, render: (r) => (r.daysAhead === null ? t('common.none') : String(r.daysAhead)) },
      { key: 'en', label: t('settings.alertRules.enabled'), render: (r) => (r.enabled ? t('common.yes') : t('common.no')) },
      { key: 'e', label: '', render: (r) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => formDialog({ title: t(`alerts.types.${r.type}`), size: 'md',
        values: { roles: r.roles, enabled: r.enabled, daysAhead: r.daysAhead },
        spec: [{ key: 'roles', label: t('settings.alertRules.roles'), type: 'checks', span: true, options: roleList.map((x) => ({ value: x.code, label: name(x) })) },
          { key: 'enabled', label: t('settings.alertRules.enabled'), type: 'bool' }, { key: 'daysAhead', label: t('settings.alertRules.daysAhead'), type: 'number', step: 1 }],
        submit: (data) => api.put(`/alert-rules/${r.type}`, { roles: data.roles, enabled: data.enabled !== false, daysAhead: data.daysAhead, version: r.version }), onSaved: draw }) }, icon('edit')) },
    ], d.items));
  }

  async function audit(page) {
    const d = await api.get('/audit', { page, size: 25 });
    replace(body, dataTable([
      { key: 'w', label: t('settings.audit.when'), render: (e) => formatDateTime(e.occurredAt) },
      { key: 'u', label: t('settings.audit.who'), render: (e) => e.actor.displayName },
      { key: 'a', label: t('settings.audit.action'), render: (e) => t(`history.${e.action}`) || e.action },
      { key: 'r', label: t('settings.audit.type'), render: (e) => h('span', { class: 'mono small', text: `${e.entityType} #${e.entityId}` }) },
      { key: 'c', label: t('settings.audit.changes'), render: (e) => (e.changes.length ? h('ul', { class: 'change-list' }, e.changes.slice(0, 6).map((c) => h('li', { text: `${fieldLabel(c.field)}: ${c.from ?? '—'} → ${c.to ?? '—'}` }))) : null) },
      { key: 'why', label: t('settings.audit.reason'), render: (e) => e.reason },
    ], d.items), pager({ page, totalPages: d.totalPages, totalItems: d.totalItems, onPage: (p) => audit(p) }));
  }

  await draw();
}
