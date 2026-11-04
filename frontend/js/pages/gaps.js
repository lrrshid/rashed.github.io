// Capability gap analysis: heatmap (current or forecast gap), department and category comparison, and the
// prioritised gap register with linked projects and the expected closure date.
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { openDrill } from '../components/drilldown.js';
import { barRows, card, dataTable, errorBox, legend, loadingBox, priorityBadge, refName } from '../components/ui.js';

export function heatmapTable(data, { onCell } = {}) {
  const max = Math.max(1, ...data.cells.map((c) => c.gap || 0));
  const head = h('tr', {}, h('th', { class: 'row', text: t('fields.department') }), data.categories.map((c) => h('th', { text: c.code })), h('th', { text: t('dashboard.total') }));
  const rows = data.departments.map((d) => {
    const cells = data.cells.filter((c) => c.departmentId === d.id);
    const total = cells.reduce((s, c) => s + (c.gap || 0), 0);
    return h('tr', {}, h('th', { class: 'row', scope: 'row', text: name(d) }),
      cells.map((c) => {
        if (c.gap === null) return h('td', { class: 'hnone', text: '·' });
        const level = c.gap === 0 ? 0 : Math.min(5, Math.ceil(c.gap / max * 5));
        const label = `${c.gap}${c.critical ? ' !' : ''}`;
        return h('td', { class: `h${level}` }, h('button', { type: 'button', text: label,
          'aria-label': `${name(d)} · ${data.categories.find((x) => x.id === c.categoryId).code}: ${label}`,
          disabled: !c.drill && !onCell, onclick: () => (onCell ? onCell(c, d) : openDrill(`${name(d)} · ${data.categories.find((x) => x.id === c.categoryId).code}`, c.drill)) }));
      }),
      h('td', { class: 'h0' }, h('strong', { text: formatCount(total) })));
  });
  return h('div', {}, h('table', { class: 'heat' }, h('thead', {}, head), h('tbody', {}, rows)),
    h('div', { class: 'legend' }, h('span', { text: t('gaps.legendCritical') })));
}

function comparison(groups, key) {
  return h('div', {}, barRows(groups.map((g) => ({
    label: key === 'department' ? name(g.department) : g.category.code,
    parts: [
      { value: Math.min(g.available, g.required), color: 'var(--chart-1)', label: t('fields.available') },
      { value: Math.max(Math.min(g.forecastAdd, g.required - Math.min(g.available, g.required)), 0), color: 'var(--chart-2)', label: t('completion.forecast') },
      { value: g.forecastGap, color: 'var(--red)', label: t('fields.forecastGap') },
    ],
    total: `${formatCount(g.gap)} / ${formatCount(g.required)}`,
    onClick: g.drill ? () => openDrill(key === 'department' ? name(g.department) : g.category.code, g.drill) : undefined,
  }))), legend([{ color: 'var(--chart-1)', label: t('fields.available') }, { color: 'var(--chart-2)', label: t('completion.forecast') },
    { color: 'var(--red)', label: t('fields.forecastGap') }]));
}

export async function render(container, ctx) {
  let forecast = ctx.query.forecast === 'true';
  const body = h('div');
  container.append(h('div', { class: 'page-head' },
    h('div', {}, h('h1', { tabindex: '-1', text: t('gaps.title') }), h('div', { class: 'page-sub', text: t('gaps.subtitle') }))), body);
  async function load() {
    replace(body, loadingBox());
    try {
      const data = await api.get('/gaps', { forecast });
      const seg = h('div', { class: 'segmented' }, [false, true].map((f) => h('button', { type: 'button', 'aria-pressed': forecast === f ? 'true' : 'false',
        text: t(f ? 'gaps.forecast' : 'gaps.current'), onclick: () => { forecast = f; ctx.setQuery({ forecast: f || undefined }); load(); } })));
      const register = data.register.filter((r) => !state.department || r.department.id === state.department);
      replace(body,
        h('div', { class: 'grid grid-2' },
          card(t('gaps.heatmap'), heatmapTable(data), { actions: seg }),
          h('div', { class: 'stack' },
            card(t('gaps.byDepartment'), comparison(data.byDepartment, 'department')),
            card(t('gaps.byCategory'), comparison(data.byCategory, 'category')))),
        h('div', { class: 'section-label' }),
        card(t('gaps.register'), dataTable([
          { key: 'name', label: t('fields.requirement'), render: (r) => h('a', { href: `/requirements/${r.id}`, text: `${r.code} · ${name(r)}` }) },
          { key: 'department', label: t('fields.department'), render: (r) => refName(r.department) },
          { key: 'category', label: t('fields.category'), render: (r) => r.category.code },
          { key: 'required', label: t('fields.required'), num: true, render: (r) => formatCount(r.required) },
          { key: 'available', label: t('fields.available'), num: true, render: (r) => h('button', { type: 'button', class: 'btn btn-sm btn-ghost', text: formatCount(r.available), onclick: () => openDrill(`${r.code} · ${t('fields.available')}`, { ...r.drill, statusGroup: 'AVAILABLE' }) }) },
          { key: 'operational', label: t('fields.operational'), num: true, render: (r) => formatCount(r.operational) },
          { key: 'acq', label: t('fields.underAcquisition'), num: true, render: (r) => formatCount(r.pipeline.UNDER_ACQUISITION || 0) },
          { key: 'dev', label: t('fields.underDevelopment'), num: true, render: (r) => formatCount(r.pipeline.UNDER_DEVELOPMENT || 0) },
          { key: 'test', label: t('fields.underTest'), num: true, render: (r) => formatCount(r.pipeline.UNDER_TEST || 0) },
          { key: 'gap', label: t('fields.gap'), num: true, render: (r) => formatCount(r.gap) },
          { key: 'fgap', label: t('fields.forecastGap'), num: true, render: (r) => formatCount(r.forecastGap) },
          { key: 'priority', label: t('fields.priority'), render: (r) => h('span', {}, priorityBadge(r.priority), r.critical ? h('span', { class: 'badge c-red no-dot', text: '!' }) : null) },
          { key: 'projects', label: t('fields.linkedProjects'), render: (r) => (r.projects.length ? r.projects.map((p) => h('a', { href: `/projects/${p.id}`, class: 'mono', text: `${p.code} ` })) : null) },
          { key: 'closure', label: t('fields.closureDate'), render: (r) => (r.closureDate ? formatDate(r.closureDate) : h('span', { class: 'muted small', text: t('fields.notClosed') })) },
        ], register)));
    } catch (error) { replace(body, errorBox(error, load)); }
  }
  await load();
}
