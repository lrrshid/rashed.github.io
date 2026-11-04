// Risk register: probability × impact matrix, critical risks, overdue mitigations, by category.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit, state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { barRows, card, dataTable, errorBox, kpiTile, loadingBox, statusBadge } from '../components/ui.js';
import { openRiskForm } from './project-forms.js';

const LEVEL_COLORS = { CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'amber', LOW: 'grey' };

export function riskColumns({ withProject = true, onEdit } = {}) {
  return [
    { key: 'code', label: t('risks.fields.code'), render: (r) => h('span', { class: 'mono', text: r.code }) },
    withProject ? { key: 'project', label: t('risks.fields.project'), render: (r) => h('a', { href: `/projects/${r.project.id}?tab=risks`, class: 'mono', text: r.project.code }) } : null,
    { key: 'title', label: t('risks.fields.title'), render: (r) => name(r, 'title') },
    { key: 'category', label: t('risks.fields.category'), render: (r) => t(`risks.categories.${r.category}`) },
    { key: 'p', label: t('risks.fields.probability'), num: true, render: (r) => String(r.probability) },
    { key: 'i', label: t('risks.fields.impact'), num: true, render: (r) => String(r.impact) },
    { key: 'score', label: t('risks.fields.score'), num: true, render: (r) => h('span', { class: `badge c-${LEVEL_COLORS[r.level]}`, text: `${r.score} · ${t(`risks.levels.${r.level}`)}` }) },
    { key: 'owner', label: t('risks.fields.owner'), render: (r) => r.ownerName },
    { key: 'mitigation', label: t('risks.fields.mitigation'), render: (r) => name(r, 'mitigation') },
    { key: 'due', label: t('risks.fields.due'), render: (r) => h('span', { class: r.mitigationOverdue ? 'badge c-red no-dot' : '', text: formatDate(r.mitigationDueDate) }) },
    { key: 'status', label: t('fields.status'), render: (r) => statusBadge('RISK', r.status) },
    onEdit ? { key: 'edit', label: '', render: (r) => h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: () => onEdit(r) }, icon('edit')) } : null,
  ].filter(Boolean);
}

export async function render(container, ctx) {
  let level = ctx.query.level || null;
  let cell = null;
  const body = h('div');
  const head = h('div', { class: 'page-head' });
  container.append(head, body);
  async function load() {
    replace(body, loadingBox());
    let d; let projects;
    try {
      [d, projects] = await Promise.all([api.get('/risks', { department: state.department || undefined }), api.get('/projects', { view: 'ACTIVE' })]);
    } catch (error) { replace(body, errorBox(error, load)); return; }
    const editable = canEdit('edit.risks');
    const context = { projects: projects.items };
    replace(head, h('div', {}, h('h1', { tabindex: '-1', text: t('risks.title') }), h('div', { class: 'page-sub', text: t('risks.subtitle') })),
      editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openRiskForm(null, context, load) }, icon('plus'), t('risks.add')) : null);
    let items = d.items;
    if (level) items = items.filter((r) => r.level === level);
    if (cell) items = items.filter((r) => r.probability === cell.p && r.impact === cell.i && r.status !== 'CLOSED');
    const k = d.kpis;
    replace(body,
      h('div', { class: 'kpis' },
        kpiTile({ label: t('risks.kpi.open'), value: formatCount(k.open), onClick: () => { level = null; cell = null; load(); } }),
        kpiTile({ label: t('risks.kpi.critical'), value: formatCount(k.critical), tone: k.critical ? 'red' : undefined, onClick: () => { level = 'CRITICAL'; cell = null; load(); } }),
        kpiTile({ label: t('risks.kpi.high'), value: formatCount(k.high), tone: k.high ? 'amber' : undefined, onClick: () => { level = 'HIGH'; cell = null; load(); } }),
        kpiTile({ label: t('risks.kpi.overdueMitigations'), value: formatCount(k.overdueMitigations), tone: k.overdueMitigations ? 'red' : undefined }),
        kpiTile({ label: t('risks.kpi.mitigating'), value: formatCount(k.mitigating) }),
        kpiTile({ label: t('risks.kpi.closed'), value: formatCount(k.closed) })),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-3' },
        card(t('risks.matrix'), riskMatrix(d.matrix, d.thresholds, (p, i) => { cell = { p, i }; level = null; load(); })),
        h('div', { class: 'span-2' }, card(t('risks.byCategory'), barRows(d.byCategory.map((c) => ({ label: t(`risks.categories.${c.category}`), parts: [{ value: c.count, color: 'var(--chart-1)', label: '' }] })))))),
      h('div', { class: 'section-label' }),
      dataTable(riskColumns({ onEdit: editable ? (r) => openRiskForm(r, context, load) : null }), items));
  }
  await load();
}

function riskMatrix(cells, th, onCell) {
  const count = (p, i) => (cells.find((c) => c.probability === p && c.impact === i) || { count: 0 }).count;
  const tone = (score) => (score >= th.critical ? '#f7c6c0' : score >= th.high ? '#fde3c2' : score >= th.medium ? '#fdf2c6' : '#dfeafb');
  const rows = [5, 4, 3, 2, 1].map((p) => h('tr', {}, h('th', { class: 'row', text: String(p) }), [1, 2, 3, 4, 5].map((i) => {
    const n = count(p, i);
    return h('td', { style: `background:${tone(p * i)}` }, n ? h('button', { type: 'button', text: String(n), 'aria-label': `${t('risks.fields.probability')} ${p} × ${t('risks.fields.impact')} ${i}: ${n}`, onclick: () => onCell(p, i) }) : h('span', { class: 'muted', text: ' ' }));
  })));
  return h('div', { dir: 'ltr' }, h('table', { class: 'heat' }, h('tbody', {}, rows,
    h('tr', {}, h('th'), [1, 2, 3, 4, 5].map((i) => h('th', { text: String(i) }))))),
  h('div', { class: 'legend' }, h('span', { text: `↑ ${t('risks.fields.probability')} · → ${t('risks.fields.impact')}` })));
}
