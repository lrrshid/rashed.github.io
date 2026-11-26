// Project profile: executive summary, six independent RAG indicators each with its stated reason, workflow path,
// milestones with Gantt, risks, issues, linked capabilities and the audit trail.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canChange, canEdit, lookupList } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatDateTime, formatMoney, formatPercent } from '../lib/format.js';
import { card, dataTable, dl, errorBox, historyList, loadingBox, meter, priorityBadge, ragDot, refName, statusBadge, tabs, toast } from '../components/ui.js';
import { gantt, rangeAround } from '../components/gantt.js';
import { openHealthNoteForm, openIssueForm, openMilestoneForm, openProjectForm, openRiskForm } from './project-forms.js';
import { issueColumns } from './issues.js';
import { milestoneColumns } from './milestones.js';
import { riskColumns } from './risks.js';

const DIMS = ['SCHEDULE', 'BUDGET', 'SCOPE', 'TESTING', 'RISKS', 'PROCUREMENT'];

export async function render(container, ctx) {
  let tab = ctx.query.tab || 'overview';
  async function load() {
    replace(container, loadingBox());
    let p;
    try { p = await api.get(`/projects/${ctx.params.id}`); } catch (error) { replace(container, errorBox(error, load)); return; }
    const editable = canEdit('edit.projects');  // add milestones
    const changeable = canChange('edit.projects');  // change, archive, judge the project
    const reload = () => load();
    const header = h('div', { class: 'card' },
      h('div', { class: 'page-head', style: 'margin:0' },
        h('div', {},
          h('div', { class: 'breadcrumb' }, h('a', { href: '/projects', text: t('nav.projects') }), h('span', { text: `› ${p.code}` })),
          h('h1', { tabindex: '-1' }, h('span', { class: 'mono', text: p.code }), ` ${name(p)}`),
          h('div', { class: 'page-sub', text: `${refName(p.type)} · ${refName(p.department)} · ${p.category ? p.category.code : ''} · ${t('projects.fields.manager')}: ${p.managerName || t('common.none')}` }),
          h('div', { class: 'actions' }, statusBadge('PROJECT', p.status), ragDot(p.health))),
        h('div', { class: 'actions' },
          changeable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openProjectForm(p, reload) }, icon('edit'), t('common.edit')) : null,
          changeable ? h('button', { type: 'button', class: 'btn', onclick: async () => {
            try { await api.post(`/projects/${p.id}/archive`, { archived: !p.archived, version: p.version }); toast(t('common.saved')); load(); } catch (e) { toast(e.message, true); }
          } }, icon(p.archived ? 'restore' : 'archive'), p.archived ? t('common.restore') : t('common.archive')) : null)),
      h('div', { class: 'section-label' }),
      h('div', { class: 'kpis' },
        stat(t('projects.fields.progress'), formatPercent(p.progressPct), meter(p.progressPct)),
        stat(t('projects.fields.stage'), refName(p.stage)),
        stat(t('projects.fields.target'), formatDate(p.targetEndDate)),
        stat(t('projects.fields.forecast'), formatDate(p.forecastEndDate)),
        stat(t('projects.fields.delay'), formatCount(p.delayDays), null, p.delayDays ? 'red' : null),
        stat(t('projects.fields.budget'), formatMoney(p.budget)),
        stat(t('projects.fields.spend'), formatMoney(p.actualSpend)),
        stat(t('projects.fields.committed'), formatMoney(p.committed))),
      p.nextActionEn || p.nextActionAr ? h('div', { class: 'notice', style: 'margin-top:10px' }, h('strong', { text: `${t('projects.fields.nextAction')}: ` }), name(p, 'nextAction')) : null);

    const tabBar = tabs(['overview', 'milestones', 'gantt', 'risks', 'issues', 'capabilities', 'activity'].map((k) => ({ key: k, label: t(`projects.tabs.${k}`) })), tab,
      (k) => { tab = k; ctx.setQuery({ tab: k }); load(); });
    const body = h('div', { class: 'stack' });
    replace(container, header, h('div', { class: 'section-label' }), tabBar, body);
    const context = { projects: [p], projectId: p.id, stages: p.workflow };

    if (tab === 'overview') {
      body.append(card(t('projects.health.title'), h('div', {},
        h('div', { class: 'grid grid-3' }, DIMS.map((dim) => {
          const ind = p.indicators[dim];
          const manual = dim === 'SCOPE' || dim === 'PROCUREMENT';
          return h('div', { class: 'card', style: `border-inline-start:4px solid var(--${ind.rag === 'GREEN' ? 'green' : ind.rag === 'AMBER' ? 'amber' : ind.rag === 'RED' ? 'red' : 'grey'})` },
            h('div', { class: 'card-head' }, h('h3', { text: t(`projects.health.dims.${dim}`) }), ragDot(ind.rag)),
            h('p', { class: 'small', text: `${t('projects.health.reason')}: ${name(ind, 'reason')}` }),
            manual && changeable ? h('button', { type: 'button', class: 'btn btn-sm', onclick: () => openHealthNoteForm(p, dim, reload) }, icon('edit'), t('common.edit')) : null);
        })),
        h('p', { class: 'small muted', style: 'margin-top:8px', text: t('projects.health.basis') })), { actions: h('span', {}, `${t('projects.health.overall')}: `, ragDot(p.health)) }));
      body.append(card(t('projects.workflow'), h('div', { class: 'actions' }, p.workflow.map((s) =>
        h('span', { class: `badge ${s.state === 'DONE' ? 'c-green' : s.state === 'CURRENT' ? 'c-blue' : 'c-grey'}`, text: `${s.order}. ${name(s)}` })))));
      body.append(h('div', { class: 'grid grid-2' },
        card(t('projects.details'), dl([
          [t('projects.fields.code'), p.code], [t('projects.fields.type'), refName(p.type)], [t('fields.department'), refName(p.department)],
          [t('fields.category'), refName(p.category)], [t('projects.fields.manager'), p.managerName],
          [t('projects.fields.supplier'), refName(p.supplier)], [t('projects.fields.contract'), p.contract ? `${p.contract.code} · ${name(p.contract)}` : null],
          [t('projects.fields.start'), formatDate(p.startDate)], [t('projects.fields.baseline'), formatDate(p.baselineEndDate)],
          [t('projects.fields.actual'), formatDate(p.actualEndDate)], [t('fields.updatedAt'), formatDateTime(p.updatedAt)],
        ])),
        h('div', { class: 'stack' },
          card(t('projects.topRisks'), h('ul', { class: 'attention' }, p.risks.filter((r) => r.status !== 'CLOSED').sort((a, b) => b.score - a.score).slice(0, 4).map((r) =>
            h('li', { class: r.level === 'CRITICAL' ? '' : 'amber' }, h('strong', { class: 'mono', text: `${r.score} ` }), name(r, 'title'))))),
          card(t('projects.topIssues'), h('ul', { class: 'attention' }, p.issues.filter((i) => !['RESOLVED', 'CLOSED'].includes(i.status)).slice(0, 4).map((i) =>
            h('li', { class: i.severity === 'CRITICAL' || i.severity === 'HIGH' ? '' : 'amber' }, h('span', { class: 'mono', text: `${i.code} ` }), name(i, 'title'))))))));
    } else if (tab === 'milestones') {
      body.append(editable ? h('div', { class: 'actions' }, h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openMilestoneForm(null, context, reload) }, icon('plus'), t('milestones.add'))) : null,
        dataTable(milestoneColumns({ withProject: false, onEdit: changeable ? (m) => openMilestoneForm(m, context, reload) : null }), p.milestones));
    } else if (tab === 'gantt') {
      body.append(projectGantt(p));
    } else if (tab === 'risks') {
      body.append(canEdit('edit.risks') ? h('div', { class: 'actions' }, h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openRiskForm(null, context, reload) }, icon('plus'), t('risks.add'))) : null,
        dataTable(riskColumns({ withProject: false, onEdit: canChange('edit.risks') ? (r) => openRiskForm(r, context, reload) : null }), p.risks));
    } else if (tab === 'issues') {
      body.append(canEdit('edit.risks') ? h('div', { class: 'actions' }, h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openIssueForm(null, context, reload) }, icon('plus'), t('issues.add'))) : null,
        dataTable(issueColumns({ withProject: false, onEdit: canChange('edit.risks') ? (i) => openIssueForm(i, context, reload) : null }), p.issues));
    } else if (tab === 'capabilities') {
      body.append(h('div', { class: 'grid grid-2' },
        card(t('projects.fields.requirements'), dataTable([
          { key: 'r', label: t('fields.requirement'), render: (x) => h('a', { href: `/requirements/${x.requirement.id}`, text: `${x.requirement.code} · ${name(x.requirement)}` }) },
          { key: 'q', label: t('projects.fields.quantity'), num: true, render: (x) => formatCount(x.quantity) },
        ], p.requirements)),
        card(t('projects.fields.models'), dataTable([
          { key: 'm', label: t('fields.model'), render: (x) => h('a', { href: `/models/${x.model.id}`, text: `${x.model.code} · ${name(x.model)}` }) },
          { key: 'rel', label: t('projects.fields.relation'), render: (x) => t(`projects.relations.${x.relation}`) },
        ], p.models))));
    } else {
      const data = await api.get(`/history/PROJECT/${p.id}`);
      body.append(card(t('projects.tabs.activity'), historyList(data.items)));
    }
  }
  await load();
}

function stat(label, value, extra, tone) {
  return h('div', { class: `kpi static ${tone ? `tone-${tone}` : ''}` }, h('span', { class: 'kpi-label', text: label }),
    h('span', { class: 'kpi-value', style: 'font-size:1.05rem', text: value }), extra || null);
}

export function projectGantt(p) {
  const rows = [{ label: `${p.code} ${name(p)}`, start: p.startDate, end: p.targetEndDate, forecastEnd: p.forecastEndDate, progress: p.progressPct, late: p.delayDays > 0 }];
  for (const m of p.milestones) {
    rows.push({ label: name(m), sub: m.ownerName, indent: true, start: m.plannedStartDate, end: m.plannedEndDate,
      forecastEnd: m.status !== 'COMPLETED' ? m.forecastEndDate : null, progress: m.progressPct, color: m.status === 'COMPLETED' ? '#12a150' : m.status === 'DELAYED' ? '#d24b3e' : '#2f6fd6',
      markers: m.major ? [{ date: m.actualEndDate || m.forecastEndDate || m.plannedEndDate, label: name(m), color: '#b9995a' }] : [] });
  }
  const today = new Date().toISOString().slice(0, 10);
  const range = rangeAround(rows, today) || { from: today, to: today };
  return gantt(rows, { ...range, today, scale: 'MONTH' });
}

export { priorityBadge, lookupList };
