// Capability completion: required, available, operational and pipeline quantities per department (or category),
// with current versus forecast completion. Every figure opens its assets.
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatPercent } from '../lib/format.js';
import { openDrill } from '../components/drilldown.js';
import { card, errorBox, loadingBox, meter, ring } from '../components/ui.js';
import { requirementTable } from './registry.js';

export function completionGroupCard(group, key) {
  const label = name(group[key]);
  const drill = (title, extra) => () => openDrill(`${label} · ${title}`, { ...group.drill, ...extra });
  const stat = (title, value, extra) => h('button', { type: 'button', class: 'kpi', onclick: extra && group.drill ? drill(title, extra) : undefined },
    h('span', { class: 'kpi-label', text: title }), h('span', { class: 'kpi-value', text: formatCount(value) }));
  return card(label, h('div', {},
    h('div', { class: 'grid', style: 'grid-template-columns: auto 1fr; align-items:center' },
      ring(group.currentPct, group.forecastPct, t('completion.current')),
      h('div', { class: 'kpis', style: 'grid-template-columns: repeat(3, minmax(0,1fr))' },
        stat(t('fields.required'), group.required),
        stat(t('fields.available'), group.available, { statusGroup: 'AVAILABLE' }),
        stat(t('fields.operational'), group.operational, { statusGroup: 'OPERATIONAL' }),
        stat(t('fields.underAcquisition'), group.pipeline.UNDER_ACQUISITION || 0, { status: ['UNDER_ACQUISITION'], statusGroup: undefined }),
        stat(t('fields.underDevelopment'), group.pipeline.UNDER_DEVELOPMENT || 0, { status: ['UNDER_DEVELOPMENT'], statusGroup: undefined }),
        stat(t('fields.underTest'), group.pipeline.UNDER_TEST || 0, { status: ['UNDER_TEST'], statusGroup: undefined }))),
    h('div', { class: 'section-label' }),
    meter(group.currentPct, group.forecastPct, true),
    h('div', { class: 'small muted', text: `${t('completion.current')} ${formatPercent(group.currentPct)} → ${t('completion.forecast')} ${formatPercent(group.forecastPct)} · ${t('fields.gap')} ${formatCount(group.gap)} · ${t('fields.forecastGap')} ${formatCount(group.forecastGap)}` })));
}

export async function render(container, ctx) {
  let by = ctx.query.by === 'category' ? 'category' : 'department';
  const body = h('div', {});
  const seg = h('div', { class: 'segmented' });
  container.append(h('div', { class: 'page-head' },
    h('div', {}, h('h1', { tabindex: '-1', text: t('completion.title') }), h('div', { class: 'page-sub', text: t('completion.subtitle') })), seg), body);
  async function load() {
    replace(seg, ...['department', 'category'].map((k) => h('button', { type: 'button', 'aria-pressed': by === k ? 'true' : 'false',
      text: t(k === 'department' ? 'completion.byDepartment' : 'completion.byCategory'), onclick: () => { by = k; ctx.setQuery({ by: k }); load(); } })));
    replace(body, loadingBox());
    try {
      const data = await api.get('/completion', { by });
      const total = { ...data.total, [by]: { nameEn: t('completion.total'), nameAr: t('completion.total') } };
      const groups = data.groups.filter((g) => !state.department || by !== 'department' || g.department.id === state.department);
      const reqs = data.requirements.filter((r) => !state.department || r.department.id === state.department);
      replace(body,
        completionGroupCard(total, by),
        h('div', { class: 'section-label' }),
        h('div', { class: 'grid grid-2' }, groups.map((g) => completionGroupCard(g, by))),
        h('div', { class: 'section-label' }),
        card(t('completion.requirements'), requirementTable(reqs)));
    } catch (error) { replace(body, errorBox(error, load)); }
  }
  await load();
}
