// Project portfolio: KPIs (each a filter), budget and spend, charts by department, status, stage, category, target
// quarter and health, and the project list.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit, lookupList, state, statusDef, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatMoney, formatPercent } from '../lib/format.js';
import { RAG_COLORS, barRows, card, colorOf, dataTable, donut, errorBox, field, kpiTile, legend, listOptions, loadingBox,
  meter, ragDot, refName, selectEl, statusBadge } from '../components/ui.js';
import { openProjectForm } from './project-forms.js';

export function projectColumns() {
  return [
    { key: 'code', label: t('projects.fields.code'), render: (p) => h('a', { href: `/projects/${p.id}`, class: 'mono', text: p.code }) },
    { key: 'name', label: t('projects.fields.name'), render: (p) => h('a', { href: `/projects/${p.id}`, text: name(p) }) },
    { key: 'type', label: t('projects.fields.type'), render: (p) => refName(p.type) },
    { key: 'department', label: t('fields.department'), render: (p) => refName(p.department) },
    { key: 'category', label: t('fields.category'), render: (p) => (p.category ? p.category.code : null) },
    { key: 'status', label: t('projects.fields.status'), render: (p) => statusBadge('PROJECT', p.status) },
    { key: 'stage', label: t('projects.fields.stage'), render: (p) => refName(p.stage) },
    { key: 'progress', label: t('projects.fields.progress'), render: (p) => h('div', { style: 'min-width:90px' }, meter(p.progressPct), h('span', { class: 'small', text: formatPercent(p.progressPct) })) },
    { key: 'target', label: t('projects.fields.target'), render: (p) => formatDate(p.targetEndDate) },
    { key: 'forecast', label: t('projects.fields.forecast'), render: (p) => formatDate(p.forecastEndDate) },
    { key: 'delay', label: t('projects.fields.delay'), num: true, render: (p) => (p.delayDays ? h('span', { class: 'badge c-red no-dot', text: String(p.delayDays) }) : '0') },
    { key: 'health', label: t('projects.fields.health'), render: (p) => ragDot(p.health) },
  ];
}

export async function render(container, ctx) {
  const filters = { view: (ctx.query.view || '').toUpperCase() || undefined, status: ctx.query.status, type: ctx.query.type,
    category: ctx.query.category, health: ctx.query.health, q: ctx.query.q };
  const body = h('div');
  const head = h('div', { class: 'page-head' });
  container.append(head, body);

  async function load() {
    const title = filters.view ? t(`projects.views.${filters.view}`) : t('projects.title');
    replace(head, h('div', {}, h('h1', { tabindex: '-1', text: title }), h('div', { class: 'page-sub', text: t('projects.subtitle') })),
      h('div', { class: 'actions' }, canEdit('edit.projects') ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openProjectForm(null, (p) => ctx.navigate(`/projects/${p.id}`)) }, icon('plus'), t('projects.add')) : null));
    replace(body, loadingBox());
    let d;
    try {
      d = await api.get('/projects', { ...clean(filters), department: state.department || undefined });
    } catch (error) { replace(body, errorBox(error, load)); return; }
    const set = (patch) => () => { Object.assign(filters, patch); ctx.setQuery(clean(filters)); load(); };
    const k = d.kpis;
    const tile = (key, value, patch, extra = {}) => kpiTile({ label: t(`projects.kpi.${key}`), value, onClick: patch ? set(patch) : undefined, ...extra });
    replace(body,
      h('div', { class: 'kpis' },
        tile('total', formatCount(k.total), { view: undefined, status: undefined, health: undefined }),
        tile('completed', formatCount(k.completed), { view: 'COMPLETED' }),
        tile('active', formatCount(k.active), { view: 'ACTIVE' }),
        tile('delayed', formatCount(k.delayed), { view: 'DELAYED' }, { tone: k.delayed ? 'red' : 'green' }),
        tile('closed', formatCount(k.closed)),
        tile('testing', formatCount(k.testing), { status: 'TESTING,FIELD_TRIALS,EVALUATION' }),
        tile('development', formatCount(k.development), { status: 'DEVELOPMENT' }),
        tile('due30', formatCount(k.due30), { view: 'DUE30' }),
        tile('due90', formatCount(k.due90), { view: 'DUE90' }),
        tile('attention', formatCount(k.attention), { view: 'ATTENTION' }, { tone: k.attention ? 'red' : undefined }),
        tile('avgProgress', formatPercent(k.avgProgress)),
        tile('budget', formatMoney(k.budget), null, { money: true }),
        tile('spend', formatMoney(k.spend), null, { money: true, title: k.spendPct !== null ? formatPercent(k.spendPct) : undefined }),
        kpiTile({ label: t('projects.kpi.criticalRisks'), value: formatCount(k.criticalRisks), tone: k.criticalRisks ? 'red' : undefined, onClick: () => ctx.navigate('/risks?level=CRITICAL') })),
      h('div', { class: 'section-label' }),
      charts(d.charts, set),
      h('div', { class: 'section-label' }),
      filterBar(set),
      dataTable(projectColumns(), d.items));
  }

  function filterBar(set) {
    const status = selectEl(statuses('PROJECT').map((s) => ({ value: s.code, label: name(s) })), filters.status, { includeEmpty: true });
    const type = selectEl(listOptions(lookupList('projectTypes')), filters.type, { includeEmpty: true });
    type.addEventListener('change', () => { filters.type = type.value || undefined; ctx.setQuery(clean(filters)); load(); });
    status.onchange = () => { filters.status = status.value || undefined; ctx.setQuery(clean(filters)); load(); };
    const cat = selectEl(listOptions(lookupList('categories'), { withCode: true }), filters.category, { includeEmpty: true });
    cat.addEventListener('change', () => { filters.category = cat.value || undefined; ctx.setQuery(clean(filters)); load(); });
    const health = selectEl(['GREEN', 'AMBER', 'RED'].map((r) => ({ value: r, label: t(`rag.${r}`) })), filters.health, { includeEmpty: true });
    health.addEventListener('change', () => { filters.health = health.value || undefined; ctx.setQuery(clean(filters)); load(); });
    return h('div', { class: 'filters' }, field(t('projects.fields.status'), status), field(t('projects.fields.type'), type),
      field(t('fields.category'), cat), field(t('projects.fields.health'), health),
      h('div', { class: 'field' }, h('span', { class: 'label', text: ' ' }), h('button', { type: 'button', class: 'btn', text: t('common.clear'),
        onclick: () => { for (const key of Object.keys(filters)) filters[key] = undefined; ctx.setQuery({}); load(); } })));
  }

  await load();
}

function charts(c, set) {
  const ragParts = (row) => ['GREEN', 'AMBER', 'RED'].map((k) => ({ value: row[k], color: RAG_COLORS[k], label: t(`rag.${k}`) }));
  const statusRows = c.byStatus.map((s) => { const def = statusDef('PROJECT', s.status); return { label: def ? name(def) : s.status, parts: [{ value: s.count, color: colorOf(def && def.color), label: '' }], onClick: set({ status: s.status, view: undefined }) }; });
  const total = c.byHealth.GREEN + c.byHealth.AMBER + c.byHealth.RED;
  const maxQ = Math.max(1, ...c.byQuarter.map((q) => q.count));
  return h('div', { class: 'grid grid-3' },
    card(t('projects.charts.byDepartment'), h('div', {}, barRows(c.byDepartment.map((r) => ({ label: name(r.department), parts: ragParts(r) }))),
      legend(['GREEN', 'AMBER', 'RED'].map((k) => ({ color: RAG_COLORS[k], label: t(`rag.${k}`) }))))),
    card(t('projects.charts.byStatus'), barRows(statusRows)),
    card(t('projects.charts.byHealth'), h('div', { class: 'grid', style: 'grid-template-columns:auto 1fr;align-items:center' },
      donut(['GREEN', 'AMBER', 'RED'].map((k) => ({ label: t(`rag.${k}`), value: c.byHealth[k], color: RAG_COLORS[k] })), formatCount(total), t('nav.projects')),
      h('ul', { class: 'status-list' }, ['GREEN', 'AMBER', 'RED'].map((k) => h('li', {}, h('button', { type: 'button', onclick: set({ health: k }) },
        h('i', { style: `background:${RAG_COLORS[k]}` }), h('span', { text: t(`rag.${k}`) }), h('strong', { text: String(c.byHealth[k]) }))))))),
    card(t('projects.charts.byStage'), barRows(c.byStage.map((s) => ({ label: refName(s.stage), parts: [{ value: s.count, color: 'var(--chart-1)', label: '' }] })))),
    card(t('projects.charts.byCategory'), barRows(c.byCategory.map((s) => ({ label: s.category.code, parts: [{ value: s.count, color: 'var(--chart-1)', label: '' }], onClick: set({ category: s.category.id }) })))),
    card(t('projects.charts.byQuarter'), h('div', { class: 'actions', style: 'align-items:flex-end;min-height:140px;direction:ltr;gap:10px' }, c.byQuarter.map((q) =>
      h('div', { style: 'display:flex;flex-direction:column;align-items:center;gap:4px' }, h('strong', { class: 'small', text: String(q.count) }),
        h('span', { style: `display:block;width:28px;height:${q.count / maxQ * 100}px;background:var(--chart-1);border-radius:3px 3px 0 0` }),
        h('span', { class: 'small muted', text: q.quarter.replace('-', ' ') }))))));
}

function clean(obj) {
  return Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== undefined && v !== null && v !== ''));
}
