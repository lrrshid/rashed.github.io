// Create / edit dialogs for projects, milestones, risks, issues and the hand-recorded health indicators.
import { api } from '../api.js';
import { lookupList, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { listOptions } from '../components/ui.js';
import { diff, formDialog } from './forms.js';

const statusOptions = (domain) => statuses(domain).filter((s) => !s.archived).map((s) => ({ value: s.code, label: name(s) }));

export async function openProjectForm(project, onSaved) {
  const types = lookupList('projectTypes');
  const stages = types.flatMap((ty) => ty.stages.map((s) => ({ value: s.id, label: `${name(ty)} · ${s.sortOrder}. ${name(s)}` })));
  const codes = project ? null : await api.get('/projects/next-code');
  const spec = [
    { key: 'code', label: t('projects.fields.code'), required: true, max: 20, readonly: Boolean(project), dir: 'ltr' },
    { key: 'statusCode', label: t('projects.fields.status'), type: 'select', required: true, options: statusOptions('PROJECT') },
    { key: 'nameEn', label: t('projects.fields.nameEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'nameAr', label: t('projects.fields.nameAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'projectTypeId', label: t('projects.fields.type'), type: 'select', required: true, options: listOptions(types) },
    { key: 'stageId', label: t('projects.fields.stage'), type: 'select', options: stages },
    { key: 'departmentId', label: t('fields.department'), type: 'select', required: true, options: listOptions(lookupList('departments')) },
    { key: 'categoryId', label: t('fields.category'), type: 'select', required: true, options: listOptions(lookupList('categories'), { withCode: true }) },
    { key: 'managerName', label: t('projects.fields.manager'), max: 160 },
    { key: 'supplierId', label: t('projects.fields.supplier'), type: 'select', options: listOptions(lookupList('organizations')) },
    { key: 'contractId', label: t('projects.fields.contract'), type: 'select', options: lookupList('contracts').map((c) => ({ value: c.id, label: `${c.code} · ${name(c)}` })) },
    { key: 'progressPct', label: t('projects.fields.progress'), type: 'number', step: 1 },
    { key: 'budget', label: t('projects.fields.budget'), type: 'number' },
    { key: 'committed', label: t('projects.fields.committed'), type: 'number' },
    { key: 'actualSpend', label: t('projects.fields.spend'), type: 'number' },
    { key: 'startDate', label: t('projects.fields.start'), type: 'date' },
    { key: 'targetEndDate', label: t('projects.fields.target'), type: 'date' },
    { key: 'forecastEndDate', label: t('projects.fields.forecast'), type: 'date' },
    { key: 'actualEndDate', label: t('projects.fields.actual'), type: 'date' },
    { key: 'nextActionEn', label: t('projects.fields.nextActionEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    { key: 'nextActionAr', label: t('projects.fields.nextActionAr'), type: 'textarea', dir: 'rtl', max: 2000 },
  ];
  const values = project ? {
    code: project.code, statusCode: project.status, nameEn: project.nameEn, nameAr: project.nameAr,
    projectTypeId: project.type && project.type.id, stageId: project.stage && project.stage.id,
    departmentId: project.department && project.department.id, categoryId: project.category && project.category.id,
    managerName: project.managerName, supplierId: project.supplier && project.supplier.id, contractId: project.contract && project.contract.id,
    progressPct: project.progressPct, budget: project.budget, committed: project.committed, actualSpend: project.actualSpend,
    startDate: project.startDate, targetEndDate: project.targetEndDate, forecastEndDate: project.forecastEndDate,
    actualEndDate: project.actualEndDate, nextActionEn: project.nextActionEn, nextActionAr: project.nextActionAr,
  } : { code: codes.project, statusCode: 'PROPOSED', progressPct: 0 };
  formDialog({
    title: project ? t('projects.editTitle', { code: project.code }) : t('projects.newTitle'), spec, values, withReason: Boolean(project),
    submit: (data) => (project ? api.patch(`/projects/${project.id}`, { ...diff(values, data), version: project.version }) : api.post('/projects', data)),
    onSaved,
  });
}

export function openHealthNoteForm(project, dimension, onSaved) {
  const current = project.indicators[dimension];
  const values = { rag: current.rag === 'GREY' ? 'GREEN' : current.rag, reasonEn: current.reasonEn, reasonAr: current.reasonAr };
  formDialog({
    title: t('projects.health.editNote', { dim: t(`projects.health.dims.${dimension}`) }), size: 'md', values,
    spec: [
      { key: 'rag', label: t('projects.fields.health'), type: 'select', required: true, options: ['GREEN', 'AMBER', 'RED'].map((r) => ({ value: r, label: t(`rag.${r}`) })) },
      { key: 'reasonEn', label: `${t('projects.health.reason')} (EN)`, type: 'textarea', dir: 'ltr', max: 2000, span: true },
      { key: 'reasonAr', label: `${t('projects.health.reason')} (ع)`, type: 'textarea', dir: 'rtl', max: 2000, span: true },
    ],
    submit: (data) => api.put(`/projects/${project.id}/health/${dimension}`, data),
    onSaved,
  });
}

function projectOptions(projects) {
  return projects.map((p) => ({ value: p.id, label: `${p.code} · ${name(p)}` }));
}

export function openMilestoneForm(milestone, { projects, projectId, stages = [] }, onSaved) {
  const spec = [
    milestone ? null : { key: 'projectId', label: t('milestones.fields.name'), type: 'select', required: true, options: projectOptions(projects) },
    { key: 'nameEn', label: t('projects.fields.nameEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'nameAr', label: t('projects.fields.nameAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('MILESTONE') },
    { key: 'ownerName', label: t('milestones.fields.owner'), max: 160 },
    { key: 'plannedStartDate', label: t('milestones.fields.plannedStart'), type: 'date', required: true },
    { key: 'plannedEndDate', label: t('milestones.fields.plannedEnd'), type: 'date', required: true },
    { key: 'forecastEndDate', label: t('milestones.fields.forecast'), type: 'date' },
    { key: 'actualEndDate', label: t('milestones.fields.actual'), type: 'date' },
    { key: 'progressPct', label: t('milestones.fields.progress'), type: 'number', step: 1 },
    { key: 'isMajor', label: t('milestones.fields.major'), type: 'bool' },
    stages.length ? { key: 'stageId', label: t('milestones.fields.stage'), type: 'select', options: stages.map((s) => ({ value: s.id, label: name(s) })) } : null,
  ].filter(Boolean);
  const values = milestone ? { nameEn: milestone.nameEn, nameAr: milestone.nameAr, statusCode: milestone.status, ownerName: milestone.ownerName,
    plannedStartDate: milestone.plannedStartDate, plannedEndDate: milestone.plannedEndDate, forecastEndDate: milestone.forecastEndDate,
    actualEndDate: milestone.actualEndDate, progressPct: milestone.progressPct, isMajor: milestone.major, stageId: milestone.stage && milestone.stage.id }
    : { projectId, statusCode: 'NOT_STARTED', progressPct: 0, isMajor: false };
  formDialog({
    title: milestone ? t('milestones.editTitle') : t('milestones.newTitle'), spec, values, withReason: Boolean(milestone),
    submit: (data) => (milestone ? api.patch(`/milestones/${milestone.id}`, { ...diff(values, data), version: milestone.version })
      : api.post('/milestones', { ...data, isMajor: Boolean(data.isMajor) })),
    onSaved,
  });
}

export async function openRiskForm(risk, { projects, projectId }, onSaved) {
  const codes = risk ? null : await api.get('/projects/next-code');
  const scores = [1, 2, 3, 4, 5].map((n) => ({ value: String(n), label: String(n) }));
  const spec = [
    { key: 'code', label: t('risks.fields.code'), required: true, readonly: Boolean(risk), dir: 'ltr' },
    risk ? null : { key: 'projectId', label: t('risks.fields.project'), type: 'select', required: true, options: projectOptions(projects) },
    { key: 'titleEn', label: t('risks.fields.titleEn'), type: 'textarea', required: true, dir: 'ltr', max: 500, span: true },
    { key: 'titleAr', label: t('risks.fields.titleAr'), type: 'textarea', required: true, dir: 'rtl', max: 500, span: true },
    { key: 'category', label: t('risks.fields.category'), type: 'select', required: true, options: Object.keys(t('risks.categories')).map((c) => ({ value: c, label: t(`risks.categories.${c}`) })) },
    { key: 'probability', label: t('risks.fields.probability'), type: 'select', required: true, options: scores },
    { key: 'impact', label: t('risks.fields.impact'), type: 'select', required: true, options: scores },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('RISK') },
    { key: 'ownerName', label: t('risks.fields.owner'), max: 160 },
    { key: 'mitigationDueDate', label: t('risks.fields.due'), type: 'date' },
    { key: 'mitigationEn', label: t('risks.fields.mitigationEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    { key: 'mitigationAr', label: t('risks.fields.mitigationAr'), type: 'textarea', dir: 'rtl', max: 2000 },
  ].filter(Boolean);
  const values = risk ? { code: risk.code, titleEn: risk.titleEn, titleAr: risk.titleAr, category: risk.category,
    probability: String(risk.probability), impact: String(risk.impact), statusCode: risk.status, ownerName: risk.ownerName,
    mitigationDueDate: risk.mitigationDueDate, mitigationEn: risk.mitigationEn, mitigationAr: risk.mitigationAr }
    : { code: codes.risk, projectId, statusCode: 'OPEN', probability: '3', impact: '3', category: 'TECHNICAL' };
  const toNumbers = (data) => ({ ...data, ...(data.probability ? { probability: Number(data.probability) } : {}), ...(data.impact ? { impact: Number(data.impact) } : {}) });
  formDialog({
    title: risk ? t('risks.editTitle', { code: risk.code }) : t('risks.newTitle'), spec, values, withReason: Boolean(risk),
    submit: (data) => (risk ? api.patch(`/risks/${risk.id}`, { ...toNumbers(diff(values, data)), version: risk.version }) : api.post('/risks', toNumbers(data))),
    onSaved,
  });
}

export async function openIssueForm(issue, { projects, projectId }, onSaved) {
  const codes = issue ? null : await api.get('/projects/next-code');
  const spec = [
    { key: 'code', label: t('issues.fields.code'), required: true, readonly: Boolean(issue), dir: 'ltr' },
    issue ? null : { key: 'projectId', label: t('issues.fields.project'), type: 'select', required: true, options: projectOptions(projects) },
    { key: 'titleEn', label: t('issues.fields.titleEn'), type: 'textarea', required: true, dir: 'ltr', max: 500, span: true },
    { key: 'titleAr', label: t('issues.fields.titleAr'), type: 'textarea', required: true, dir: 'rtl', max: 500, span: true },
    { key: 'severity', label: t('issues.fields.severity'), type: 'select', required: true, options: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((s) => ({ value: s, label: t(`priority.${s}`) })) },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('ISSUE') },
    { key: 'ownerName', label: t('issues.fields.owner'), max: 160 },
    { key: 'raisedDate', label: t('issues.fields.raised'), type: 'date' },
    { key: 'targetDate', label: t('issues.fields.target'), type: 'date' },
    { key: 'isEscalated', label: t('issues.fields.escalated'), type: 'bool' },
    { key: 'resolutionEn', label: t('issues.fields.resolutionEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    { key: 'resolutionAr', label: t('issues.fields.resolutionAr'), type: 'textarea', dir: 'rtl', max: 2000 },
  ].filter(Boolean);
  const values = issue ? { code: issue.code, titleEn: issue.titleEn, titleAr: issue.titleAr, severity: issue.severity, statusCode: issue.status,
    ownerName: issue.ownerName, raisedDate: issue.raisedDate, targetDate: issue.targetDate, isEscalated: issue.escalated,
    resolutionEn: issue.resolutionEn, resolutionAr: issue.resolutionAr }
    : { code: codes.issue, projectId, statusCode: 'OPEN', severity: 'MEDIUM', isEscalated: false };
  formDialog({
    title: issue ? t('issues.editTitle', { code: issue.code }) : t('issues.newTitle'), spec, values, withReason: Boolean(issue),
    submit: (data) => (issue ? api.patch(`/issues/${issue.id}`, { ...diff(values, data), version: issue.version })
      : api.post('/issues', { ...data, isEscalated: Boolean(data.isEscalated) })),
    onSaved,
  });
}
