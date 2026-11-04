// Strategic timeline (/timeline): every project's bar from start to target, slip to forecast, major milestones,
// at monthly to five-year scale. Portfolio Gantt (/gantt): all projects with expandable milestone rows.
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { lookupList, state, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { card, colorOf, errorBox, field, legend, listOptions, loadingBox, selectEl } from '../components/ui.js';
import { gantt, rangeAround } from '../components/gantt.js';

const SPANS = { MONTH: [60, 240, 'MONTH'], QUARTER: [90, 540, 'MONTH'], YEAR: [180, 900, 'QUARTER'], Y3: [365, 1095, 'QUARTER'], Y5: [365, 1825, 'YEAR'] };

export async function render(container, ctx) {
  const portfolio = window.location.pathname === '/gantt';
  let scale = ctx.query.scale || 'Y3';
  const filters = { type: ctx.query.type || '', category: ctx.query.category || '', status: ctx.query.status || '' };
  let projectFilter = ctx.query.project || '';
  let showMilestones = ctx.query.milestones !== 'false';
  let showCompleted = ctx.query.completed === 'true';
  const head = h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: portfolio ? t('gantt.title') : t('timeline.title') }),
    portfolio ? null : h('div', { class: 'page-sub', text: t('timeline.subtitle') })));
  const controls = h('div', { class: 'card' });
  const body = h('div');
  container.append(head, controls, h('div', { class: 'section-label' }), body);

  async function load() {
    replace(body, loadingBox());
    let d;
    try {
      d = await api.get('/timeline', { department: state.department || undefined, type: filters.type || undefined,
        category: filters.category || undefined, status: filters.status || undefined, view: showCompleted ? undefined : 'ACTIVE' });
    } catch (error) { replace(body, errorBox(error, load)); return; }
    drawControls(d.items);
    const types = Object.fromEntries(lookupList('projectTypes').map((ty) => [ty.id, ty]));
    let items = d.items;
    if (projectFilter) items = items.filter((p) => p.id === projectFilter);
    const rows = [];
    let detail = {};
    if (portfolio) {
      const details = await Promise.all(items.map((p) => api.get(`/projects/${p.id}`)));
      detail = Object.fromEntries(details.map((p) => [p.id, p]));
    }
    for (const p of items) {
      const ty = p.type ? types[p.type.id] : null;
      rows.push({ label: `${p.code} · ${name(p)}`, sub: `${p.department ? p.department.code : ''} · ${p.category ? p.category.code : ''} · ${ty ? name(ty) : ''}`,
        href: `/projects/${p.id}`, start: p.startDate, end: p.targetEndDate, forecastEnd: p.forecastEndDate, progress: p.progressPct,
        color: colorOf(ty && ty.color), late: p.delayDays > 0,
        markers: (p.milestones || []).map((m) => ({ date: m.actualEndDate || m.forecastEndDate || m.plannedEndDate, label: name(m), color: m.status === 'COMPLETED' ? '#12a150' : '#b9995a' })) });
      if (portfolio && showMilestones && detail[p.id]) {
        for (const m of detail[p.id].milestones) {
          rows.push({ label: name(m), sub: m.ownerName, indent: true, start: m.plannedStartDate, end: m.plannedEndDate,
            forecastEnd: m.status !== 'COMPLETED' ? m.forecastEndDate : null, progress: m.progressPct,
            color: m.status === 'COMPLETED' ? '#12a150' : m.status === 'DELAYED' ? '#d24b3e' : '#2f6fd6' });
        }
      }
    }
    const [back, ahead, tick] = SPANS[scale] || SPANS.Y3;
    const todayMs = Date.parse(`${d.today}T00:00:00Z`);
    const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
    const range = portfolio ? (rangeAround(rows, d.today) || { from: d.today, to: d.today }) : { from: iso(todayMs - back * 86_400_000), to: iso(todayMs + ahead * 86_400_000) };
    replace(body, card(null, h('div', {},
      gantt(rows, { ...range, today: d.today, scale: portfolio ? 'MONTH' : tick, width: Math.max(1100, container.clientWidth - 40) }),
      legend([...lookupList('projectTypes').map((ty) => ({ color: colorOf(ty.color), label: name(ty) })),
        { color: '#b9995a', label: t('timeline.legendMilestone') }, { color: '#d24b3e', label: t('timeline.legendSlip') }]))));
  }

  function drawControls(items) {
    const save = () => ctx.setQuery({ scale, ...filters, project: projectFilter || undefined, milestones: showMilestones ? undefined : 'false', completed: showCompleted ? 'true' : undefined });
    const scales = h('div', { class: 'segmented' }, Object.keys(SPANS).map((k) => h('button', { type: 'button', 'aria-pressed': scale === k ? 'true' : 'false', text: t(`timeline.scales.${k}`), onclick: () => { scale = k; save(); load(); } })));
    const sel = (key, options, label) => {
      const s = selectEl(options, filters[key], { includeEmpty: true });
      s.addEventListener('change', () => { filters[key] = s.value; save(); load(); });
      return field(label, s);
    };
    const project = selectEl(items.map((p) => ({ value: p.id, label: `${p.code} · ${name(p)}` })), projectFilter, { includeEmpty: true, emptyLabel: t('gantt.allProjects') });
    project.addEventListener('change', () => { projectFilter = project.value; save(); load(); });
    replace(controls, h('div', { class: 'filters', style: 'margin:0' },
      portfolio ? field(t('gantt.project'), project) : h('div', { class: 'field wide' }, h('span', { class: 'label', text: ' ' }), scales),
      sel('type', listOptions(lookupList('projectTypes')), t('projects.fields.type')),
      sel('category', listOptions(lookupList('categories'), { withCode: true }), t('fields.category')),
      sel('status', statuses('PROJECT').map((s) => ({ value: s.code, label: name(s) })), t('projects.fields.status')),
      portfolio ? h('label', { class: 'checks' }, h('input', { type: 'checkbox', checked: showMilestones || undefined, onchange: (e) => { showMilestones = e.target.checked; save(); load(); } }), t('gantt.showMilestones')) : null,
      h('label', { class: 'checks' }, h('input', { type: 'checkbox', checked: showCompleted || undefined, onchange: (e) => { showCompleted = e.target.checked; save(); load(); } }), t('gantt.showCompleted'))));
  }
  await load();
}
