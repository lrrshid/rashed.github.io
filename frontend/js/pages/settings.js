// Settings (system administrators): configurable lists, statuses, workflows by project type, specification fields,
// AI levels, business rules, roles and permissions, users, alert rules and the audit history. No code changes needed.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { isAdmin, lookupList, setLookups, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatDateTime } from '../lib/format.js';
import { card, dataTable, errorBox, listOptions, loadingBox, lookupName, pager, tabs, toast } from '../components/ui.js';
import { diff, formDialog } from './forms.js';
import { CONNECTION_TABS, renderConnections } from './connections.js';
import { downloadUserTemplate, openUserImport } from './user-import.js';
import { fieldLabel } from './field-labels.js';
import { DEFAULT_THEME, PRESETS, applyTheme, effectiveTheme, normalise, rememberTheme, setPersonalPalette } from '../lib/theme.js';

const TABS = ['departments', 'categories', 'sites', 'units', 'organizations', 'contracts', 'statuses', 'workflows', 'specFields', 'ai',
  'appearance', 'rules', 'roles', 'users', 'alertRules', ...CONNECTION_TABS, 'audit'];
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
    case 'units': return [codeField(editing), ...nameFields,
      { key: 'parentId', label: t('settings.unitParent'), type: 'select', options: listOptions(lookupList('units').filter((u) => !u.parentId)) }, sortField];
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
  // A direct way to the interface colours (the Appearance tab), at the top of the page.
  const colours = h('button', { type: 'button', class: 'btn btn-primary', onclick: () => { tab = 'appearance'; ctx.setQuery({ tab }); draw(); } },
    icon('palette'), t('settings.appearance.open'));
  container.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: t('settings.title') }),
    h('div', { class: 'page-sub', text: t('settings.subtitle') })), h('div', { class: 'actions' }, colours)), bar, body);
  const drawTabs = () => replace(bar, tabs(TABS.map((k) => ({ key: k, label: t(`settings.tabs.${k}`) })), tab, (k) => { tab = k; ctx.setQuery({ tab: k }); draw(); }));

  async function refreshLookups() { setLookups(await api.get('/lookups')); }

  async function draw() {
    drawTabs();
    if (tab !== 'appearance') applyTheme(effectiveTheme());   // leave an unsaved colour preview behind
    replace(body, loadingBox());
    try {
      if (['departments', 'categories', 'sites', 'units', 'organizations', 'contracts', 'statuses', 'specFields'].includes(tab)) await simpleList(tab);
      else if (tab === 'workflows') await workflows();
      else if (tab === 'ai') await aiSettings();
      else if (tab === 'appearance') await appearance();
      else if (tab === 'rules') await rules();
      else if (tab === 'roles') await roles();
      else if (tab === 'users') await users();
      else if (tab === 'alertRules') await alertRules();
      else if (CONNECTION_TABS.includes(tab)) await renderConnections(body, tab, draw);
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
      kind === 'units' ? { key: 'parent', label: t('settings.unitParent'), render: (e) => (e.parentId ? lookupName('units', e.parentId) : null) } : null,
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
    replace(body, h('div', { class: 'grid grid-2' }, d.items.filter((s) => !s.key.startsWith('ui.')).map((s) => {
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

  // Interface colours: a ready-made palette or four colours of one's own, previewed at once, saved for everyone.
  async function appearance() {
    const row = (await api.get('/settings')).items.find((s) => s.key === 'ui.theme');
    let current = normalise(row.value);
    const KEYS = ['sidebar', 'primary', 'accent', 'background'];
    const same = (a, b) => KEYS.every((k) => a[k] === b[k]);
    const swatches = (c) => h('span', { class: 'theme-swatches' }, KEYS.map((k) => h('span', { class: 'theme-swatch', style: `background:${c[k]}` })));
    const presetButtons = Object.entries(PRESETS).map(([key, colours]) => {
      const btn = h('button', { type: 'button', class: 'theme-preset', 'aria-pressed': 'false', onclick: () => set(colours) },
        swatches(colours), h('span', { text: t(`settings.appearance.presets.${key}`) }));
      return { btn, colours };
    });
    const inputs = {};
    const codes = {};
    const colourRows = KEYS.map((k) => {
      inputs[k] = h('input', { type: 'color', 'aria-label': t(`settings.appearance.${k}`) });
      codes[k] = h('span', { class: 'mono' });
      inputs[k].addEventListener('input', () => set({ ...current, [k]: inputs[k].value }));
      return h('label', { class: 'theme-color' }, inputs[k], h('span', {}, h('div', { text: t(`settings.appearance.${k}`) }), codes[k]));
    });
    function set(colours) {
      current = normalise(colours);
      applyTheme(current);
      for (const k of KEYS) { inputs[k].value = current[k]; codes[k].textContent = current[k]; }
      for (const p of presetButtons) p.btn.setAttribute('aria-pressed', same(p.colours, current) ? 'true' : 'false');
    }
    const save = h('button', { type: 'button', class: 'btn btn-primary', text: t('settings.appearance.save'), onclick: async () => {
      save.disabled = true;
      try {
        await api.put('/settings/ui.theme', { value: current, version: row.version, reason: t('settings.appearance.reason') });
        rememberTheme(current);
        setPersonalPalette(null);   // this device shows what was just saved for everyone
        toast(t('settings.appearance.saved'));
        await draw();
      } catch (e) { toast(e.message, true); } finally { save.disabled = false; }
    } });
    replace(body,
      card(t('settings.appearance.presetsTitle'), h('div', {}, h('p', { class: 'muted small', text: t('settings.appearance.intro') }),
        h('div', { class: 'theme-presets' }, presetButtons.map((p) => p.btn)))),
      h('div', { class: 'section-label' }),
      card(t('settings.appearance.custom'), h('div', { class: 'theme-colors' }, colourRows), {
        actions: h('span', { class: 'actions' },
          h('button', { type: 'button', class: 'btn', text: t('settings.appearance.reset'), onclick: () => set(DEFAULT_THEME) }), save) }));
    set(current);
  }

  // A role's level in the organisation's structure: 1 at the top, 0 = not placed (shown only; grants nothing).
  const levelField = { key: 'tier', label: t('settings.roles.level'), type: 'select', required: true,
    options: Array.from({ length: 11 }, (_, n) => ({ value: String(n), label: n ? t('settings.roles.levelN', { n }) : t('settings.roles.level0') })) };

  // What a role may do, in words, from its permissions: every permission; add, view, change and archive; add and view
  // (edit.* without records.change); view only.
  function roleKind(r, all) {
    if (all.every((p) => r.permissions.includes(p))) return 'all';
    const adds = r.permissions.some((p) => p.startsWith('edit.'));
    if (adds) return r.permissions.includes('records.change') ? 'change' : 'add';
    return 'view';
  }

  function editRole(r) {
    formDialog({ title: t('settings.roles.editTitle', { name: name(r) }), size: 'md',
      values: { nameEn: r.nameEn, nameAr: r.nameAr, tier: String(r.tier || 0) },
      spec: [...nameFields, levelField],
      submit: (data) => api.patch(`/admin/roles/${r.id}`, { nameEn: data.nameEn, nameAr: data.nameAr, tier: Number(data.tier), version: r.version }),
      onSaved: async () => { await refreshLookups(); draw(); } });
  }

  // The organisation's structure (owner, 25 Nov 2026): one row per level, top down, the roles of a level side by
  // side, each with what it may do and how many active people have it; roles without a level are listed under it.
  function structure(d) {
    const byLevel = new Map();
    for (const r of d.items) {
      const level = r.tier || 0;
      if (!byLevel.has(level)) byLevel.set(level, []);
      byLevel.get(level).push(r);
    }
    const roleCard = (r) => {
      const kind = roleKind(r, d.permissions);
      return h('div', { class: `org-role org-${kind}` },
        h('div', { class: 'org-name', text: name(r) }),
        h('div', { class: 'org-perms', text: t(`settings.roles.summary.${kind}`) }),
        h('div', { class: 'org-meta muted small', text: t('settings.roles.people', { n: r.activeUsers })
          + (r.scope === 'DEPARTMENT' ? ` · ${t('settings.roles.DEPARTMENT')}` : '') }),
        h('button', { type: 'button', class: 'btn btn-sm btn-ghost org-edit', 'aria-label': `${t('settings.roles.editRole')}: ${name(r)}`,
          title: t('settings.roles.editRole'), onclick: () => editRole(r) }, icon('edit')));
    };
    const levels = [...byLevel.keys()].filter((level) => level > 0).sort((a, b) => a - b);
    const unplaced = byLevel.get(0) || [];
    return card(t('settings.roles.structure'), h('div', {},
      h('p', { class: 'muted small', text: t('settings.roles.structureHint') }),
      h('div', { class: 'org-chart' }, levels.map((level) => h('div', { class: 'org-level', role: 'group',
        'aria-label': t('settings.roles.levelN', { n: level }) }, byLevel.get(level).map(roleCard)))),
      unplaced.length ? h('div', { class: 'org-unplaced' }, h('div', { class: 'section-label', text: t('settings.roles.notPlaced') }),
        h('div', { class: 'org-level' }, unplaced.map(roleCard))) : null));
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
    replace(body, h('div', { class: 'toolbar' }, h('span'), h('button', { type: 'button', class: 'btn btn-primary', onclick: () => formDialog({ title: t('settings.roles.newRole'), size: 'md', values: { scope: 'ALL', tier: '0' },
      spec: [{ key: 'code', label: t('settings.roles.code'), required: true, max: 30, dir: 'ltr' }, ...nameFields,
        { key: 'scope', label: t('settings.roles.scope'), type: 'select', required: true, options: ['ALL', 'DEPARTMENT'].map((s) => ({ value: s, label: t(`settings.roles.${s}`) })) },
        levelField],
      submit: (data) => api.post('/admin/roles', { ...data, tier: Number(data.tier), permissions: ['view'] }), onSaved: async () => { await refreshLookups(); draw(); } }) }, icon('plus'), t('settings.roles.newRole'))),
    structure(d),
    h('div', { class: 'table-wrap' }, h('table', { class: 'data' }, h('thead', {}, head), h('tbody', {}, rows))));
  }

  async function users() {
    const d = await api.get('/users', { size: 100 });
    const roleOptions = lookupList('roles').map((r) => ({ value: r.code, label: name(r) }));
    // A new person starts with the lowest role of the structure (the user), else the last role listed.
    const placed = lookupList('roles').filter((r) => r.tier).sort((a, b) => b.tier - a.tier);
    const firstRole = (placed[0] || lookupList('roles').slice(-1)[0] || {}).code || '';
    const deptOptions = listOptions(lookupList('departments'));
    const open = (u) => formDialog({ title: u ? t('settings.users.editTitle', { name: u.displayName }) : t('settings.users.newTitle'), size: 'md', withReason: Boolean(u),
      values: u ? { username: u.username, displayName: u.displayName, role: u.role, active: u.active, departmentIds: u.departments.map((x) => x.id) } : { role: firstRole, departmentIds: [] },
      spec: [{ key: 'username', label: t('settings.users.username'), required: true, max: 120, dir: 'ltr', readonly: Boolean(u) },
        { key: 'displayName', label: t('settings.users.displayName'), max: 160 },
        { key: 'role', label: t('settings.users.role'), type: 'select', required: true, options: roleOptions },
        u ? { key: 'active', label: t('settings.users.active'), type: 'bool' } : { key: 'password', label: t('settings.users.password'), max: 200 },
        { key: 'departmentIds', label: t('settings.users.departments'), type: 'checks', span: true, options: deptOptions,
          showWhen: (v) => (lookupList('roles').find((r) => r.code === v.role) || {}).scope === 'DEPARTMENT' }],
      submit: (data) => (u ? api.patch(`/users/${u.id}`, { ...diff({ displayName: u.displayName, role: u.role, active: u.active, departmentIds: u.departments.map((x) => x.id) }, data), version: u.version })
        : api.post('/users', { username: data.username, displayName: data.displayName, role: data.role, password: data.password || undefined, departmentIds: data.departmentIds })),
      onSaved: draw });
    // Many people at once: the Excel template, then the import (pages/user-import.js); one person: the form.
    replace(body, h('div', { class: 'toolbar' }, h('span'), h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'btn', onclick: downloadUserTemplate }, icon('download'), t('settings.users.import.template')),
      h('button', { type: 'button', class: 'btn', onclick: () => openUserImport(draw) }, icon('file'), t('settings.users.import.open')),
      h('button', { type: 'button', class: 'btn btn-primary', onclick: () => open(null) }, icon('plus'), t('settings.users.add')))),
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
