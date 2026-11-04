// Milestones across the portfolio: planned, actual and forecast dates with slippage and status.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatPercent } from '../lib/format.js';
import { dataTable, errorBox, kpiTile, loadingBox, statusBadge } from '../components/ui.js';

export function milestoneColumns({ withProject = true, onEdit } = {}) {
  return [
    withProject ? { key: 'project', label: t('projects.fields.code'), render: (m) => h('a', { href: `/projects/${m.project.id}?tab=milestones`, class: 'mono', text: m.project.code }) } : null,
    { key: 'name', label: t('milestones.fields.name'), render: (m) => h('span', {}, name(m), m.major ? h('span', { class: 'badge c-amber no-dot', style: 'margin-inline-start:6px', text: '◆' }) : null) },
    withProject ? { key: 'department', label: t('fields.department'), render: (m) => name(m.project.department) } : null,
    { key: 'owner', label: t('milestones.fields.owner'), render: (m) => m.ownerName },
    { key: 'ps', label: t('milestones.fields.plannedStart'), render: (m) => formatDate(m.plannedStartDate) },
    { key: 'pe', label: t('milestones.fields.plannedEnd'), render: (m) => formatDate(m.plannedEndDate) },
    { key: 'ae', label: t('milestones.fields.actual'), render: (m) => formatDate(m.actualEndDate) },
    { key: 'fe', label: t('milestones.fields.forecast'), render: (m) => formatDate(m.forecastEndDate) },
    { key: 'status', label: t('fields.status'), render: (m) => statusBadge('MILESTONE', m.status) },
    { key: 'progress', label: t('milestones.fields.progress'), num: true, render: (m) => formatPercent(m.progressPct) },
    { key: 'slip', label: t('milestones.fields.slip'), num: true, render: (m) => (m.slipDays > 0 ? h('span', { class: `badge ${m.overdue ? 'c-red' : 'c-amber'} no-dot`, text: String(m.slipDays) }) : '0') },
    onEdit ? { key: 'edit', label: '', render: (m) => h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: () => onEdit(m) }, icon('edit')) } : null,
  ].filter(Boolean);
}

export async function render(container, ctx) {
  let majorOnly = ctx.query.majorOnly === 'true';
  let overdueOnly = ctx.query.overdue === 'true';
  const body = h('div');
  container.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: t('milestones.title') }))), body);
  async function load() {
    replace(body, loadingBox());
    try {
      const d = await api.get('/milestones', { majorOnly: majorOnly || undefined, department: state.department || undefined });
      const items = overdueOnly ? d.items.filter((m) => m.overdue) : d.items;
      const toggle = h('label', { class: 'checks' }, h('input', { type: 'checkbox', checked: majorOnly || undefined, onchange: (e) => { majorOnly = e.target.checked; ctx.setQuery({ majorOnly: majorOnly || undefined }); load(); } }), t('milestones.majorOnly'));
      replace(body,
        h('div', { class: 'kpis' }, Object.entries(d.kpis).map(([k, v]) => kpiTile({ label: t(`milestones.kpi.${k}`), value: formatCount(v), tone: k === 'overdue' && v ? 'red' : undefined,
          onClick: k === 'overdue' ? () => { overdueOnly = !overdueOnly; load(); } : undefined }))),
        h('div', { class: 'toolbar', style: 'margin-top:10px' }, toggle),
        dataTable(milestoneColumns(), items));
    } catch (error) { replace(body, errorBox(error, load)); }
  }
  await load();
}
