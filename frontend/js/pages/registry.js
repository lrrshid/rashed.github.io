// Capability registry: assets (table or cards, twelve filters, saved views), capability models, requirements.
// Also the per-category card view (/capabilities/category/UAV).
import { api, download } from '../api.js';
import { debounce, h, icon, replace } from '../lib/dom.js';
import { can, canEdit, lookupList, state, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatMoney, formatPercent } from '../lib/format.js';
import { assetColumns, withDepartment } from '../components/drilldown.js';
import { categoryGlyph, dataTable, errorBox, field, listOptions, loadingBox, meter, pager, priorityBadge, refName,
  selectEl, statusBadge, tabs, toast } from '../components/ui.js';
import { openAssetForm, openModelForm, openRequirementForm } from './forms.js';

const FILTER_KEYS = ['q', 'department', 'category', 'model', 'status', 'site', 'manufacturer', 'acquisitionYear',
  'readiness', 'warranty', 'statusGroup', 'requirement', 'sort', 'dir'];

export async function render(container, ctx) {
  const categoryCode = ctx.params.code ? ctx.params.code.toUpperCase() : null;
  const category = categoryCode ? lookupList('categories').find((c) => c.code === categoryCode) : null;
  const filters = Object.fromEntries(FILTER_KEYS.filter((k) => ctx.query[k]).map((k) => [k, ctx.query[k]]));
  let tab = ctx.query.tab || 'assets';
  let view = ctx.query.view || (category ? 'cards' : 'table');
  let page = Number(ctx.query.page || 0);

  const head = h('div', { class: 'page-head' });
  const tabBar = h('div');
  const body = h('div');
  container.append(head, tabBar, body);

  function persist() {
    ctx.setQuery({ ...filters, tab: tab === 'assets' ? undefined : tab, view: view === (category ? 'cards' : 'table') ? undefined : view, page: page || undefined });
  }

  function drawHead() {
    const title = category ? t('registry.categoryTitle', { code: category.code, name: name(category) }) : t('registry.title');
    const add = [];
    if (tab === 'assets' && canEdit('edit.assets')) add.push(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openAssetForm(null, () => draw()) }, icon('plus'), t('registry.addAsset')));
    if (tab === 'models' && canEdit('edit.models')) add.push(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openModelForm(null, () => draw()) }, icon('plus'), t('registry.addModel')));
    if (tab === 'requirements' && canEdit('edit.requirements')) add.push(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openRequirementForm(null, () => draw()) }, icon('plus'), t('registry.addRequirement')));
    replace(head,
      h('div', {}, h('div', { class: 'breadcrumb' }, h('a', { href: '/capabilities', text: t('nav.capabilities') }), category ? h('span', { text: `› ${category.code}` }) : null),
        h('h1', { tabindex: '-1', text: title }), h('div', { class: 'page-sub', text: t('registry.subtitle') })),
      h('div', { class: 'actions' }, add));
    replace(tabBar, tabs([
      { key: 'assets', label: t('registry.tabAssets') },
      { key: 'models', label: t('registry.tabModels') },
      { key: 'requirements', label: t('registry.tabRequirements') },
    ], tab, (k) => { tab = k; page = 0; persist(); draw(); }));
  }

  async function draw() {
    drawHead();
    if (tab === 'assets') return drawAssets();
    if (tab === 'models') return drawModels();
    return drawRequirements();
  }

  // ---------------------------------------------------------------- assets
  const listBox = h('div');
  async function drawAssets() {
    replace(body, filterBar(), toolbar(), listBox);
    await loadAssets();
  }

  function filterSelect(key, options, label) {
    const sel = selectEl(options, filters[key], { includeEmpty: true });
    sel.addEventListener('change', () => { if (sel.value) filters[key] = sel.value; else delete filters[key]; page = 0; persist(); loadAssets(); });
    return field(label, sel);
  }

  function filterBar() {
    const search = h('input', { class: 'input', type: 'search', value: filters.q || '', placeholder: t('top.search') });
    const onSearch = debounce(() => { if (search.value.trim()) filters.q = search.value.trim(); else delete filters.q; page = 0; persist(); loadAssets(); }, 300);
    search.addEventListener('input', onSearch);
    const years = [];
    for (let y = new Date().getFullYear(); y >= 2015; y -= 1) years.push({ value: String(y), label: String(y) });
    const models = lookupList('models');
    return h('div', { class: 'card' }, h('div', { class: 'filters' },
      h('div', { class: 'field search' }, h('label', { text: t('common.search') }), search),
      filterSelect('department', listOptions(lookupList('departments')), t('fields.department')),
      category ? null : filterSelect('category', listOptions(lookupList('categories'), { withCode: true }), t('fields.category')),
      filterSelect('model', models.filter((m) => !category || (m.category && m.category.id === category.id)).map((m) => ({ value: m.id, label: name(m) })), t('fields.model')),
      filterSelect('status', statuses('ASSET').map((s) => ({ value: s.code, label: name(s) })), t('fields.status')),
      filterSelect('statusGroup', ['AVAILABLE', 'OPERATIONAL', 'PIPELINE'].map((g) => ({ value: g, label: t(`statusGroups.${g}`) })), t('common.filters')),
      filterSelect('site', listOptions(lookupList('sites')), t('fields.site')),
      filterSelect('manufacturer', lookupList('organizations').filter((o) => o.kind !== 'SUPPLIER').map((o) => ({ value: o.id, label: name(o) })), t('fields.manufacturer')),
      filterSelect('acquisitionYear', years, t('fields.year')),
      filterSelect('readiness', ['HIGH', 'MEDIUM', 'LOW'].map((b) => ({ value: b, label: t(`bands.${b}`) })), t('fields.readinessBand')),
      filterSelect('warranty', ['ACTIVE', 'EXPIRED'].map((b) => ({ value: b, label: t(`warrantyStates.${b}`) })), t('fields.warrantyActive')),
      h('div', { class: 'field' }, h('span', { class: 'label', text: ' ' }),
        h('button', { type: 'button', class: 'btn', text: t('common.clear'), onclick: () => { for (const k of Object.keys(filters)) delete filters[k]; page = 0; persist(); draw(); } }))));
  }

  const viewsBox = h('div', { class: 'actions' });
  function toolbar() {
    const segment = h('div', { class: 'segmented', role: 'group' },
      h('button', { type: 'button', 'aria-pressed': view === 'table' ? 'true' : 'false', onclick: () => { view = 'table'; persist(); draw(); } }, icon('list'), ` ${t('common.table')}`),
      h('button', { type: 'button', 'aria-pressed': view === 'cards' ? 'true' : 'false', onclick: () => { view = 'cards'; persist(); draw(); } }, icon('grid'), ` ${t('common.cards')}`));
    loadViews();
    return h('div', { class: 'toolbar' }, viewsBox, h('div', { class: 'actions' }, segment,
      can('export') ? h('button', { type: 'button', class: 'btn', onclick: () => download('/assets.csv', { ...query(), lang: document.documentElement.lang }) }, icon('download'), t('common.exportCsv')) : null));
  }

  async function loadViews() {
    try {
      const data = await api.get('/saved-views', { page: 'registry' });
      const sel = h('select', { class: 'select', 'aria-label': t('common.savedViews') }, h('option', { value: '', text: t('common.savedViews') }),
        data.items.map((v) => h('option', { value: v.id, text: v.name })));
      sel.addEventListener('change', () => {
        const v = data.items.find((x) => x.id === sel.value);
        if (!v) return;
        for (const k of Object.keys(filters)) delete filters[k];
        Object.assign(filters, v.filters);
        page = 0; persist(); draw();
      });
      const save = h('button', { type: 'button', class: 'btn btn-sm', text: t('common.saveView'), onclick: async () => {
        const label = window.prompt(t('common.viewName'));
        if (!label) return;
        try { await api.post('/saved-views', { page: 'registry', name: label.slice(0, 80), filters }); toast(t('common.saved')); loadViews(); } catch (e) { toast(e.message, true); }
      } });
      const del = h('button', { type: 'button', class: 'btn btn-sm btn-ghost', text: t('common.deleteView'), onclick: async () => {
        if (!sel.value) return;
        try { await api.del(`/saved-views/${sel.value}`); loadViews(); } catch (e) { toast(e.message, true); }
      } });
      replace(viewsBox, sel, save, del);
    } catch { replace(viewsBox); }
  }

  function query() {
    const q = withDepartment(filters);
    if (category) q.category = category.id;
    return q;
  }

  async function loadAssets() {
    replace(listBox, loadingBox());
    try {
      const data = await api.get('/assets', { ...query(), page, size: view === 'cards' ? 48 : 25 });
      const list = view === 'cards' ? assetCards(data.items) : dataTable(assetColumns(), data.items, {
        sort: filters.sort, dir: filters.dir,
        onSort: (key) => { filters.dir = filters.sort === key && filters.dir !== 'desc' ? 'desc' : 'asc'; filters.sort = key; persist(); loadAssets(); },
      });
      replace(listBox, list, pager({ page, totalPages: data.totalPages, totalItems: data.totalItems, onPage: (p) => { page = p; persist(); loadAssets(); } }));
    } catch (error) {
      replace(listBox, errorBox(error, loadAssets));
    }
  }

  function assetCards(items) {
    if (!items.length) return h('div', { class: 'empty', text: t('common.noResults') });
    return h('div', { class: 'asset-cards' }, items.map((a) => h('a', { class: 'asset-card', href: `/assets/${a.id}` },
      h('div', { class: 'top' }, icon(categoryGlyph(a.category && a.category.code), 'glyph'),
        h('div', {}, h('div', { class: 'title' }, h('span', { class: 'mono', text: a.code }), ` · ${refName(a.model)}`),
          h('div', { class: 'sub', text: `${a.department ? a.department.code : ''} · ${refName(a.site)}` }))),
      h('div', { class: 'actions' }, statusBadge('ASSET', a.status)),
      a.readiness.operational !== null
        ? h('div', {}, h('div', { class: 'sub', text: `${t('fields.opReadiness')} ${formatPercent(a.readiness.operational)}` }), meter(a.readiness.operational))
        : h('div', { class: 'sub', text: a.expectedDeliveryDate ? `${t('fields.deliveryDate')} ${formatDate(a.expectedDeliveryDate)}` : '' }))));
  }

  // ---------------------------------------------------------------- models
  async function drawModels() {
    replace(body, loadingBox());
    try {
      const data = await api.get('/models', { category: category ? category.id : undefined });
      replace(body, dataTable([
        { key: 'code', label: t('fields.code'), render: (m) => h('a', { href: `/models/${m.id}`, class: 'mono', text: m.code }) },
        { key: 'name', label: t('fields.model'), render: (m) => h('a', { href: `/models/${m.id}`, text: name(m) }) },
        { key: 'category', label: t('fields.category'), render: (m) => (m.category ? m.category.code : null) },
        { key: 'role', label: t('fields.role'), render: (m) => name(m, 'role') },
        { key: 'manufacturer', label: t('fields.manufacturer'), render: (m) => refName(m.manufacturer) },
        { key: 'assets', label: t('fields.assets'), num: true, render: (m) => formatCount(m.assetCounts.total) },
        { key: 'ready', label: t('fields.operational'), num: true, render: (m) => formatCount((m.assetCounts.byStatus.READY || 0) + (m.assetCounts.byStatus.READY_LIMITED || 0)) },
        { key: 'cost', label: t('fields.unitCost'), num: true, render: (m) => formatMoney(m.unitCost) },
      ], data.items));
    } catch (error) { replace(body, errorBox(error, drawModels)); }
  }

  // ---------------------------------------------------------------- requirements
  async function drawRequirements() {
    replace(body, loadingBox());
    try {
      const data = await api.get('/requirements', { department: state.department || undefined, category: category ? category.id : undefined });
      replace(body, requirementTable(data.items));
    } catch (error) { replace(body, errorBox(error, drawRequirements)); }
  }

  await draw();
}

export function requirementTable(items) {
  return dataTable([
    { key: 'code', label: t('fields.code'), render: (r) => h('a', { href: `/requirements/${r.id}`, class: 'mono', text: r.code }) },
    { key: 'name', label: t('fields.requirement'), render: (r) => h('a', { href: `/requirements/${r.id}`, text: name(r) }) },
    { key: 'department', label: t('fields.department'), render: (r) => refName(r.department) },
    { key: 'category', label: t('fields.category'), render: (r) => (r.category ? r.category.code : null) },
    { key: 'required', label: t('fields.required'), num: true, render: (r) => formatCount(r.required) },
    { key: 'available', label: t('fields.available'), num: true, render: (r) => formatCount(r.available) },
    { key: 'operational', label: t('fields.operational'), num: true, render: (r) => formatCount(r.operational) },
    { key: 'pipeline', label: t('fields.pipeline'), num: true, render: (r) => formatCount(r.pipelineTotal) },
    { key: 'gap', label: t('fields.gap'), num: true, render: (r) => formatCount(r.gap) },
    { key: 'current', label: t('fields.currentCompletion'), num: true, render: (r) => formatPercent(r.currentPct) },
    { key: 'forecast', label: t('fields.forecastCompletion'), num: true, render: (r) => formatPercent(r.forecastPct) },
    { key: 'priority', label: t('fields.priority'), render: (r) => priorityBadge(r.priority) },
  ], items);
}
