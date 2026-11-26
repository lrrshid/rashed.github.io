// Capability model profile: the platform, its assets by status, structured technical capabilities (fields per
// category, administrators can add custom ones), linked requirements and projects, and its audit trail.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canChange, lookupList, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatMoney, formatNumber } from '../lib/format.js';
import { assetColumns } from '../components/drilldown.js';
import { card, categoryGlyph, dataTable, dl, errorBox, historyList, kpiTile, loadingBox, refName, tabs, toast } from '../components/ui.js';
import { openModelForm, openSpecsForm } from './forms.js';
import { fieldLabel } from './field-labels.js';
import { requirementTable } from './registry.js';

export async function render(container, ctx) {
  let tab = ctx.query.tab || 'assets';
  async function load() {
    replace(container, loadingBox());
    let model;
    try { model = await api.get(`/models/${ctx.params.id}`); } catch (error) { replace(container, errorBox(error, load)); return; }
    const counts = model.assetCounts.byStatus;
    const actions = h('div', { class: 'actions' });
    if (canChange('edit.models')) {
      actions.append(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openModelForm(model, load) }, icon('edit'), t('common.edit')));
      actions.append(h('button', { type: 'button', class: 'btn', onclick: async () => {
        try { await api.post(`/models/${model.id}/archive`, { archived: !model.archived, version: model.version }); toast(t('common.saved')); load(); } catch (e) { toast(e.message, true); }
      } }, icon(model.archived ? 'restore' : 'archive'), model.archived ? t('common.restore') : t('common.archive')));
    }
    const header = h('div', { class: 'card' }, h('div', { class: 'profile-head' },
      icon(categoryGlyph(model.category && model.category.code), 'profile-glyph'),
      h('div', { class: 'profile-main' },
        h('div', { class: 'breadcrumb' }, h('a', { href: '/capabilities?tab=models', text: t('nav.capabilities') }), ' › ',
          model.category ? h('a', { href: `/capabilities/category/${model.category.code}`, text: model.category.code }) : null),
        h('h1', { tabindex: '-1', text: name(model) }),
        h('div', { class: 'page-sub', text: `${model.code} · ${name(model, 'role')}` }),
        dl([[t('fields.category'), refName(model.category)], [t('fields.manufacturer'), refName(model.manufacturer)],
          [t('fields.unitCost'), formatMoney(model.unitCost)]])),
      actions));
    const kpis = h('div', { class: 'kpis' },
      kpiTile({ label: t('fields.assets'), value: formatCount(model.assetCounts.total) }),
      ...statuses('ASSET').filter((s) => counts[s.code]).map((s) => kpiTile({ label: name(s), value: formatCount(counts[s.code]) })));
    const tabBar = tabs(['assets', 'specs', 'ai', 'requirements', 'activity'].map((k) => ({ key: k, label: t(`model.tabs.${k}`) })), tab, (k) => { tab = k; ctx.setQuery({ tab: k }); load(); });
    const body = h('div', { class: 'stack' });
    replace(container, header, h('div', { class: 'section-label' }), kpis, h('div', { class: 'section-label' }), tabBar, body);

    if (tab === 'assets') {
      const data = await api.get('/assets', { model: model.id, size: 100 });
      body.append(dataTable(assetColumns(), data.items));
    } else if (tab === 'specs') {
      const fields = lookupList('specFields').filter((f) => !f.archived && model.category && f.categoryId === model.category.id);
      const sections = {};
      for (const f of fields) (sections[f.section] = sections[f.section] || []).push(f);
      const grid = h('div', { class: 'grid grid-2' }, Object.entries(sections).map(([section, list]) => card(t(`model.sections.${section}`),
        dl(list.map((f) => [`${name(f)}${f.unit ? ` (${f.unit})` : ''}`, specValue(model.specs[f.code], f)])))));
      body.append(canChange('edit.models') ? h('div', { class: 'actions' }, h('button', { type: 'button', class: 'btn', onclick: () => openSpecsForm(model, load) }, icon('edit'), t('model.specsEdit'))) : null, grid);
    } else if (tab === 'ai') {
      const { modelAiPanel } = await import('./operations.js');
      body.append(await modelAiPanel(model, load));
    } else if (tab === 'requirements') {
      const data = await api.get('/requirements');
      body.append(requirementTable(data.items.filter((r) => model.requirementIds.includes(r.id))));
    } else {
      const data = await api.get(`/history/CAPABILITY_MODEL/${model.id}`);
      body.append(card(t('model.tabs.activity'), historyList(data.items, fieldLabel)));
    }
  }
  await load();
}

function specValue(value, f) {
  if (value === undefined || value === null || value === '') return null;
  if (f.dataType === 'BOOL') return h('span', { class: `badge ${value ? 'c-green' : 'c-grey'}`, text: value ? t('common.yes') : t('common.no') });
  if (f.dataType === 'NUMBER') return formatNumber(value, 2);
  return String(value);
}
