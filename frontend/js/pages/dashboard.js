// Executive dashboard (/) and dashboard analytics (/analytics): the capability position in about 30 seconds.
// Every tile, cell, bar and ring opens its source records (drill-down) or the page that lists them.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { state, statusDef } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { openDrill } from '../components/drilldown.js';
import { barRows, card, dataTable, donut, errorBox, kpiTile, legend, loadingBox, ring } from '../components/ui.js';
import { heatmapTable } from './gaps.js';
import { navigate } from '../router.js';
import { capabilityScene, followPointer } from '../components/scene.js';

const COLOR_VARS = { green: '#12804a', amber: '#e3a92b', red: '#d24b3e', blue: '#2f6fd6', purple: '#6b52b8', teal: '#0f9488',
  grey: '#9aa3aa', orange: '#e0782b', pink: '#c94f8c', dark: '#41505c' };
const RAG_COLORS = { GREEN: '#12a150', AMBER: '#e3a92b', RED: '#d24b3e' };

export async function render(container, ctx) {
  const analytics = Boolean(ctx.meta.analytics);
  async function load() {
    replace(container, loadingBox());
    let d;
    try {
      d = await api.get('/dashboard', { department: state.department || undefined });
    } catch (error) { replace(container, errorBox(error, load)); return; }
    const scope = d.department ? name(d.department) : t('common.allDepartments');
    const summaryButton = (cls) => h('a', { class: cls, href: '/reports?report=executive-summary' }, icon('file'), t('dashboard.summaryButton'));
    // Home page: a banner with the animated capability scene, the emblem and the page title.
    const head = !analytics ? h('section', { class: 'hero' }, capabilityScene('banner'),
      h('div', { class: 'hero-content' },
        h('div', { class: 'hero-brand' }, h('img', { class: 'hero-logo', src: '/assets/icons/ng-logo.png', alt: '' }),
          h('div', {}, h('div', { class: 'hero-kicker', text: t('app.name') }),
            h('h1', { tabindex: '-1', text: t('dashboard.title') }),
            h('div', { class: 'hero-sub', text: t('dashboard.subtitle', { date: formatDate(d.asOf), scope }) }))),
        h('div', { class: 'actions' }, h('a', { class: 'btn btn-hero', href: '/analytics', text: t('nav.analytics') }),
          summaryButton('btn btn-hero')))) : h('div', { class: 'page-head' },
      h('div', {}, h('h1', { tabindex: '-1', text: analytics ? t('nav.analytics') : t('dashboard.title') }),
        h('div', { class: 'page-sub', text: t('dashboard.subtitle', { date: formatDate(d.asOf), scope }) })),
      h('div', { class: 'actions' },
        h('a', { class: 'btn', href: '/', text: t('dashboard.title') }), summaryButton('btn')));
    replace(container, head);
    if (!analytics) followPointer(head);

    const tile = (key, k, extra = {}) => kpiTile({
      label: t(`dashboard.kpi.${key}`), value: formatCount(k.value), trend: k.trend, lowerIsBetter: k.lowerIsBetter,
      tone: extra.tone, onClick: k.drill ? () => openDrill(t(`dashboard.kpi.${key}`), k.drill) : k.link ? () => navigate(k.link) : undefined,
    });
    if (!analytics) {
      const inv = d.inventory; const pipe = d.pipeline; const port = d.portfolio;
      container.append(
        h('div', { class: 'section-label', text: t('dashboard.inventory') }),
        h('div', { class: 'kpis' }, tile('capabilities', inv.capabilities), tile('assets', inv.assets), tile('ready', inv.ready, { tone: 'green' }),
          tile('maintenance', inv.maintenance, { tone: 'amber' }), tile('notReady', inv.notReady, { tone: 'red' }), tile('awaiting', inv.awaiting),
          tile('writtenOff', inv.writtenOff)),
        h('div', { class: 'section-label', text: t('dashboard.pipeline') }),
        h('div', { class: 'kpis' }, tile('acquisition', pipe.acquisition), tile('development', pipe.development), tile('test', pipe.test),
          tile('criticalGaps', pipe.criticalGaps, { tone: pipe.criticalGaps.value ? 'red' : 'green' })),
        h('div', { class: 'section-label', text: t('dashboard.portfolio') }),
        h('div', { class: 'kpis' }, tile('activeProjects', port.activeProjects), tile('devProjects', port.devProjects),
          tile('testProjects', port.testProjects), tile('delayedProjects', port.delayedProjects, { tone: port.delayedProjects.value ? 'red' : 'green' }),
          tile('due30', port.due30), tile('due90', port.due90)),
        h('div', { class: 'section-label' }),
        card(t('dashboard.attention'), d.attention.length ? h('ul', { class: 'attention' }, d.attention.map((a) =>
          h('li', { class: a.severity === 'AMBER' ? 'amber' : '' }, h('a', { href: a.link, text: name(a, 'text') })))) : h('div', { class: 'empty', text: '—' }),
        { actions: h('span', { class: 'muted small', text: String(d.attention.length) }) }),
        h('div', { class: 'section-label' }),
        h('div', { class: 'grid grid-3' }, h('div', { class: 'span-2' }, matrixCard(d.matrix)), statusCard(d.statusDistribution)),
        h('div', { class: 'section-label' }));
    }
    container.append(
      h('div', { class: 'grid grid-2' }, completionRings(d.completion.groups), currentVsForecast(d.completion.groups)),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-2' }, card(t('dashboard.gapHeatmap'), heatmapTable(d.heatmap), { actions: h('a', { class: 'btn btn-sm', href: '/gaps', text: t('nav.gaps') }) }), sitesCard(d.sites)),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-2' }, portfolioCard(d.projects), timelineCard(d.projects.byQuarter)));
  }
  await load();
}

function matrixCard(m) {
  const head = h('tr', {}, h('th', { scope: 'col', text: t('fields.department') }), m.categories.map((c) => h('th', { class: 'num', scope: 'col', text: c.code })), h('th', { class: 'num', text: t('dashboard.total') }));
  const rows = m.departments.map((d) => {
    const cells = m.cells.filter((c) => c.departmentId === d.id);
    return h('tr', {}, h('th', { scope: 'row', text: name(d) }), cells.map((c) => h('td', { class: 'num' },
      c.total ? h('button', { type: 'button', class: 'btn btn-sm btn-ghost', onclick: () => openDrill(`${name(d)} · ${m.categories.find((x) => x.id === c.categoryId).code}`, c.drill),
        'aria-label': `${name(d)} ${m.categories.find((x) => x.id === c.categoryId).code}` },
      h('strong', { text: formatCount(c.current) }), h('span', { class: 'muted small', text: ` / ${formatCount(c.pipeline)}` })) : h('span', { class: 'muted', text: '·' }))),
    h('td', { class: 'num' }, h('strong', { text: formatCount(cells.reduce((s, c) => s + c.total, 0)) })));
  });
  return card(t('dashboard.matrix'), h('div', { class: 'table-wrap' }, h('table', { class: 'data' }, h('thead', {}, head), h('tbody', {}, rows))),
    { foot: `${t('dashboard.current')} / ${t('dashboard.pipelineCol')}` });
}

function statusCard(rows) {
  const total = rows.reduce((s, r) => s + r.count, 0);
  const segs = rows.filter((r) => r.count).map((r) => { const def = statusDef('ASSET', r.status); return { label: def ? name(def) : r.status, value: r.count, color: COLOR_VARS[def ? def.color : 'grey'] }; });
  return card(t('dashboard.statusDistribution'), h('div', { class: 'grid', style: 'grid-template-columns: auto 1fr; align-items:center' },
    donut(segs, formatCount(total), t('fields.assets')),
    h('ul', { class: 'status-list' }, rows.filter((r) => r.count).map((r) => {
      const def = statusDef('ASSET', r.status);
      return h('li', {}, h('button', { type: 'button', onclick: () => openDrill(def ? name(def) : r.status, r.drill) },
        h('i', { style: `background:${COLOR_VARS[def ? def.color : 'grey']}` }), h('span', { text: def ? name(def) : r.status }),
        h('strong', { class: 'mono', text: formatCount(r.count) })));
    }))));
}

function completionRings(groups) {
  return card(t('dashboard.completionByDept'), h('div', { class: 'actions', style: 'justify-content:space-around' },
    groups.map((g) => ring(g.currentPct, g.forecastPct, name(g.department), g.drill ? () => openDrill(name(g.department), g.drill) : undefined))),
  { foot: legend([{ color: '#2f6fd6', label: t('completion.current') }, { color: '#8fd0b4', label: t('completion.forecast') }]) });
}

function currentVsForecast(groups) {
  return card(t('dashboard.currentVsForecast'), h('div', { class: 'bar-rows' }, groups.map((g) => h('div', {},
    h('div', { class: 'small', text: `${name(g.department)} · ${t('fields.required')} ${g.required} · ${t('fields.available')} ${g.available} · ${t('fields.gap')} ${g.gap}` }),
    h('div', { class: 'meter tall' }, h('span', { class: 'forecast', style: `width:${g.forecastPct || 0}%` }), h('span', { style: `width:${g.currentPct || 0}%` }))))),
  { foot: t('completion.subtitle') });
}

function sitesCard(sites) {
  return card(t('dashboard.sites'), h('div', {}, barRows(sites.map((s) => ({
    label: name(s.site), parts: [{ value: s.ready, color: 'var(--chart-1)', label: t('dashboard.readyAssets') }, { value: s.notReady, color: 'var(--chart-3)', label: t('dashboard.notReadyAssets') }],
    onClick: () => openDrill(name(s.site), s.drill),
  }))), legend([{ color: 'var(--chart-1)', label: t('dashboard.readyAssets') }, { color: 'var(--chart-3)', label: t('dashboard.notReadyAssets') }])));
}

function portfolioCard(p) {
  const segs = ['GREEN', 'AMBER', 'RED'].map((k) => ({ label: t(`rag.${k}`), value: p.byHealth[k], color: RAG_COLORS[k] }));
  const rows = p.byStatus.map((s) => { const def = statusDef('PROJECT', s.status); return { label: def ? name(def) : s.status, parts: [{ value: s.count, color: COLOR_VARS[def ? def.color : 'grey'], label: '' }], onClick: () => navigate(`/projects?status=${s.status}`) }; });
  return card(t('dashboard.portfolioHealth'), h('div', { class: 'grid', style: 'grid-template-columns: auto 1fr; align-items:center' },
    donut(segs, formatCount(p.total), t('nav.projects')), barRows(rows)),
  { actions: h('a', { class: 'btn btn-sm', href: '/projects', text: t('nav.projects') }), foot: legend(segs.map((s) => ({ color: s.color, label: `${s.label} ${s.value}` }))) });
}

function timelineCard(quarters) {
  const max = Math.max(1, ...quarters.map((q) => q.GREEN + q.AMBER + q.RED));
  const bars = h('div', { class: 'actions', style: 'align-items:flex-end; gap:14px; min-height:150px; direction:ltr' }, quarters.map((q) => {
    const total = q.GREEN + q.AMBER + q.RED;
    return h('div', { style: 'display:flex;flex-direction:column;align-items:center;gap:4px' },
      h('strong', { class: 'small', text: String(total) }),
      h('div', { style: `display:flex;flex-direction:column-reverse;width:34px;height:${total / max * 110}px` },
        ['GREEN', 'AMBER', 'RED'].map((k) => (q[k] ? h('span', { title: `${t(`rag.${k}`)}: ${q[k]}`, style: `flex:${q[k]};background:${RAG_COLORS[k]}` }) : null))),
      h('span', { class: 'small muted', text: q.quarter.replace('-', ' ') }));
  }));
  return card(t('dashboard.timeline'), bars, { actions: h('a', { class: 'btn btn-sm', href: '/timeline', text: t('nav.timeline') }) });
}

export { dataTable };
