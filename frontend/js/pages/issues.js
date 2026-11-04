// Issues management: tracked separately from risks, with severity, owner, target date and escalation.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit, state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { dataTable, errorBox, kpiTile, loadingBox, priorityBadge, statusBadge } from '../components/ui.js';
import { openIssueForm } from './project-forms.js';

export function issueColumns({ withProject = true, onEdit } = {}) {
  return [
    { key: 'code', label: t('issues.fields.code'), render: (i) => h('span', { class: 'mono', text: i.code }) },
    withProject ? { key: 'project', label: t('issues.fields.project'), render: (i) => h('a', { href: `/projects/${i.project.id}?tab=issues`, class: 'mono', text: i.project.code }) } : null,
    { key: 'title', label: t('issues.fields.title'), render: (i) => name(i, 'title') },
    { key: 'severity', label: t('issues.fields.severity'), render: (i) => priorityBadge(i.severity) },
    { key: 'owner', label: t('issues.fields.owner'), render: (i) => i.ownerName },
    { key: 'raised', label: t('issues.fields.raised'), render: (i) => formatDate(i.raisedDate) },
    { key: 'target', label: t('issues.fields.target'), render: (i) => h('span', { class: i.overdue ? 'badge c-red no-dot' : '', text: formatDate(i.targetDate) }) },
    { key: 'status', label: t('fields.status'), render: (i) => statusBadge('ISSUE', i.status) },
    { key: 'escalated', label: t('issues.fields.escalated'), render: (i) => (i.escalated ? h('span', { class: 'badge c-red', text: t('common.yes') }) : t('common.no')) },
    { key: 'resolution', label: t('issues.fields.resolution'), render: (i) => name(i, 'resolution') },
    onEdit ? { key: 'edit', label: '', render: (i) => h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: () => onEdit(i) }, icon('edit')) } : null,
  ].filter(Boolean);
}

export async function render(container, ctx) {
  let filter = ctx.query.filter || null;
  const head = h('div', { class: 'page-head' });
  const body = h('div');
  container.append(head, body);
  async function load() {
    replace(body, loadingBox());
    let d; let projects;
    try {
      [d, projects] = await Promise.all([api.get('/issues', { department: state.department || undefined }), api.get('/projects', { view: 'ACTIVE' })]);
    } catch (error) { replace(body, errorBox(error, load)); return; }
    const editable = canEdit('edit.risks');
    const context = { projects: projects.items };
    replace(head, h('div', {}, h('h1', { tabindex: '-1', text: t('issues.title') }), h('div', { class: 'page-sub', text: t('issues.subtitle') })),
      editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openIssueForm(null, context, load) }, icon('plus'), t('issues.add')) : null);
    const filters = { open: (i) => !['RESOLVED', 'CLOSED'].includes(i.status), critical: (i) => i.severity === 'CRITICAL' && !['RESOLVED', 'CLOSED'].includes(i.status),
      escalated: (i) => i.escalated && !['RESOLVED', 'CLOSED'].includes(i.status), overdue: (i) => i.overdue, resolved: (i) => ['RESOLVED', 'CLOSED'].includes(i.status) };
    const items = filter && filters[filter] ? d.items.filter(filters[filter]) : d.items;
    replace(body,
      h('div', { class: 'kpis' }, Object.entries(d.kpis).map(([k, v]) => kpiTile({ label: t(`issues.kpi.${k}`), value: formatCount(v),
        tone: ['critical', 'escalated', 'overdue'].includes(k) && v ? 'red' : undefined, onClick: () => { filter = filter === k ? null : k; ctx.setQuery({ filter: filter || undefined }); load(); } }))),
      h('div', { class: 'section-label' }),
      dataTable(issueColumns({ onEdit: editable ? (i) => openIssueForm(i, context, load) : null }), items));
  }
  await load();
}
