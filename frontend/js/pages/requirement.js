// Capability requirement: what is operationally required, how much of it exists, what is on its way, the gap and
// the projects expected to close it. Every number opens its assets.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatPercent } from '../lib/format.js';
import { openDrill } from '../components/drilldown.js';
import { card, dataTable, dl, errorBox, historyList, kpiTile, loadingBox, meter, priorityBadge, refName, statusBadge, toast } from '../components/ui.js';
import { openRequirementForm } from './forms.js';
import { fieldLabel } from './field-labels.js';

export async function render(container, ctx) {
  async function load() {
    replace(container, loadingBox());
    let r;
    try { r = await api.get(`/requirements/${ctx.params.id}`); } catch (error) { replace(container, errorBox(error, load)); return; }
    const drill = (title, extra) => () => openDrill(`${r.code} · ${title}`, { ...r.drill, ...extra });
    const actions = h('div', { class: 'actions' });
    if (canEdit('edit.requirements')) {
      actions.append(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openRequirementForm(r, load) }, icon('edit'), t('common.edit')));
      actions.append(h('button', { type: 'button', class: 'btn', onclick: async () => {
        try { await api.post(`/requirements/${r.id}/archive`, { archived: !r.archived, version: r.version }); toast(t('common.saved')); load(); } catch (e) { toast(e.message, true); }
      } }, icon(r.archived ? 'restore' : 'archive'), r.archived ? t('common.restore') : t('common.archive')));
    }
    const history = h('div', {}, loadingBox());
    replace(container,
      h('div', { class: 'page-head' }, h('div', {},
        h('div', { class: 'breadcrumb' }, h('a', { href: '/capabilities?tab=requirements', text: t('registry.tabRequirements') })),
        h('h1', { tabindex: '-1', text: `${r.code} · ${name(r)}` }),
        h('div', { class: 'actions' }, priorityBadge(r.priority), r.critical ? h('span', { class: 'badge c-red', text: t('gaps.critical') }) : null)), actions),
      h('div', { class: 'kpis' },
        kpiTile({ label: t('fields.required'), value: formatCount(r.required) }),
        kpiTile({ label: t('fields.available'), value: formatCount(r.available), onClick: drill(t('fields.available'), { statusGroup: 'AVAILABLE' }) }),
        kpiTile({ label: t('fields.operational'), value: formatCount(r.operational), onClick: drill(t('fields.operational'), { statusGroup: 'OPERATIONAL' }) }),
        kpiTile({ label: t('fields.pipeline'), value: formatCount(r.pipelineTotal), onClick: drill(t('fields.pipeline'), { statusGroup: 'PIPELINE' }) }),
        kpiTile({ label: t('fields.gap'), value: formatCount(r.gap), tone: r.gap ? 'red' : 'green' }),
        kpiTile({ label: t('fields.forecastGap'), value: formatCount(r.forecastGap), tone: r.forecastGap ? 'amber' : 'green' })),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-2' },
        card(t('completion.currentForecast'), h('div', {}, meter(r.currentPct, r.forecastPct, true),
          h('p', { class: 'small muted', text: `${formatPercent(r.currentPct)} → ${formatPercent(r.forecastPct)}` }),
          dl([[t('fields.department'), refName(r.department)], [t('fields.category'), refName(r.category)],
            [t('fields.targetDate'), formatDate(r.targetDate)], [t('fields.closureDate'), r.closureDate ? formatDate(r.closureDate) : t('fields.notClosed')],
            [t('fields.models'), (r.models || []).map((m) => h('a', { href: `/models/${m.id}`, text: `${name(m)} ` }))]]))),
        card(t('fields.linkedProjects'), dataTable([
          { key: 'code', label: t('fields.code'), render: (p) => h('a', { href: `/projects/${p.id}`, class: 'mono', text: p.code }) },
          { key: 'name', label: t('nav.projects'), render: (p) => name(p) },
          { key: 'status', label: t('fields.status'), render: (p) => statusBadge('PROJECT', p.status) },
          { key: 'qty', label: t('fields.requiredQty'), num: true, render: (p) => formatCount(p.quantity) },
          { key: 'fc', label: t('completion.forecast'), render: (p) => (p.countsInForecast ? t('common.yes') : t('common.no')) },
        ], r.projects || []))),
      h('div', { class: 'section-label' }),
      card(t('asset.tabs.activity'), history));
    try {
      const data = await api.get(`/history/CAPABILITY_REQUIREMENT/${r.id}`);
      replace(history, historyList(data.items, fieldLabel));
    } catch (error) { replace(history, errorBox(error)); }
  }
  await load();
}
