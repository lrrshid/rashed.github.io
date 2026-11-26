// Testing & evaluation (/testing), maintenance & technical readiness (/maintenance), AI capabilities (/ai),
// development potential (/development) and decision support (/decision).
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canChange, canEdit, isAdmin, lookupList, state, statusDef, statuses } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatMoney, formatNumber, formatPercent } from '../lib/format.js';
import { barRows, card, colorOf, dataTable, errorBox, kpiTile, legend, listOptions, loadingBox, meter, priorityBadge,
  refName, statusBadge } from '../components/ui.js';
import { attachAll, canAttach, checkFiles, slotMark, slotRow } from '../components/attachments.js';
import { openModal } from '../components/modal.js';
import { diff, formDialog } from './forms.js';

const statusOptions = (domain) => statuses(domain).filter((s) => !s.archived).map((s) => ({ value: s.code, label: name(s) }));
const head = (title, sub, actions) => h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: title }),
  sub ? h('div', { class: 'page-sub', text: sub }) : null), actions || null);
// Units that conduct tests, as select options: each directorate followed by its sections ("— section").
function unitOptions() {
  const units = lookupList('units').filter((u) => !u.archived);
  return units.filter((u) => !u.parentId).flatMap((d) => [{ value: d.id, label: name(d) },
    ...units.filter((u) => u.parentId === d.id).map((u) => ({ value: u.id, label: `— ${name(u)}` }))]);
}
const editBtn = (onClick) => h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('common.edit'), onclick: onClick }, icon('edit'));

export async function render(container, ctx) {
  const page = window.location.pathname.slice(1);
  const pages = { testing, maintenance, 'maintenance/capability': capabilityMaintenance, ai, development, decision };
  await pages[page](container, ctx);
}

// ---------------------------------------------------------------- testing
async function testing(container, ctx) {
  const body = h('div');
  container.append(body);
  // The conducting unit: a directorate (the tests of all its sections) or one section; the first directorate by
  // default. Kept in the address bar.
  const units = unitOptions();
  let unit = (ctx && ctx.query.unit) || (units[0] ? units[0].value : '');
  function unitFilter() {
    const sel = h('select', { class: 'select', 'aria-label': t('testing.fields.unit') },
      units.map((o) => h('option', { value: o.value, text: o.label })));
    sel.value = unit;
    sel.addEventListener('change', () => { unit = sel.value; if (ctx) ctx.setQuery({ unit }); load(); });
    return sel;
  }
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/tests', { department: state.department || undefined, unit: unit || undefined }); } catch (e) { replace(body, errorBox(e, load)); return; }
    const editable = canEdit('edit.testing');
    const changeable = canChange('edit.testing');
    const k = d.kpis;
    replace(body,
      head(t('testing.title'), null, h('div', { class: 'actions' }, unitFilter(),
        editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => testForm(null, load) }, icon('plus'), t('testing.add')) : null)),
      h('div', { class: 'kpis' }, ['total', 'internal', 'external', 'planned', 'inProgress', 'passed', 'conditional', 'failed', 'upcoming90'].map((key) =>
        kpiTile({ label: t(`testing.kpi.${key}`), value: formatCount(k[key]), tone: key === 'failed' && k[key] ? 'red' : key === 'passed' ? 'green' : undefined })),
      kpiTile({ label: t('testing.kpi.passRate'), value: formatPercent(k.passRate) })),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-2' },
        card(t('testing.byModel'), h('div', {}, barRows(d.byModel.map((m) => ({ label: name(m.model), parts: [
          { value: m.PASSED, color: '#12a150', label: t('testing.kpi.passed') }, { value: m.CONDITIONAL, color: '#e3a92b', label: t('testing.kpi.conditional') },
          { value: m.FAILED, color: '#d24b3e', label: t('testing.kpi.failed') }] }))),
        legend([{ color: '#12a150', label: t('testing.kpi.passed') }, { color: '#e3a92b', label: t('testing.kpi.conditional') }, { color: '#d24b3e', label: t('testing.kpi.failed') }]))),
        card(t('testing.timeline'), h('ul', { class: 'timeline' }, d.items.slice(0, 10).map((e) => h('li', {},
          h('div', {}, h('strong', { class: 'mono', text: `${e.code} ` }), name(e, 'title'), ' ', statusBadge('TEST', e.status)),
          h('div', { class: 'muted small', text: `${formatDate(e.testDate)} · ${t(`testing.types.${e.testType}`)} · ${refName(e.model)}${e.unit ? ` · ${name(e.unit)}` : ''}${e.score !== null ? ` · ${e.score}/100` : ''}` }),
          e.resultEn ? h('div', { class: 'small', text: name(e, 'result') }) : null))))),
      h('div', { class: 'section-label' }),
      dataTable([
        { key: 'code', label: t('testing.fields.code'), render: (e) => h('span', { class: 'mono', text: e.code }) },
        { key: 'title', label: t('testing.fields.title'), render: (e) => name(e, 'title') },
        { key: 'model', label: t('testing.fields.model'), render: (e) => (e.model ? h('a', { href: `/models/${e.model.id}`, text: name(e.model) }) : null) },
        { key: 'type', label: t('testing.fields.type'), render: (e) => t(`testing.types.${e.testType}`) },
        { key: 'date', label: t('testing.fields.date'), render: (e) => formatDate(e.testDate) },
        { key: 'site', label: t('testing.fields.site'), render: (e) => refName(e.site) },
        { key: 'dept', label: t('fields.department'), render: (e) => refName(e.department) },
        { key: 'unit', label: t('testing.fields.unit'), render: (e) => refName(e.unit) },
        { key: 'project', label: t('testing.fields.project'), render: (e) => (e.project ? h('a', { href: `/projects/${e.project.id}`, class: 'mono', text: e.project.code }) : null) },
        { key: 'status', label: t('fields.status'), render: (e) => statusBadge('TEST', e.status) },
        { key: 'score', label: t('testing.fields.score'), num: true, render: (e) => (e.score === null ? null : String(e.score)) },
        changeable ? { key: 'edit', label: '', render: (e) => editBtn(() => testForm(e, load)) } : null,
      ].filter(Boolean), d.items));
  }
  await load();
}

async function testForm(test, onSaved) {
  const codes = test ? null : await api.get('/operations/next-code');
  const projects = (await api.get('/projects', { view: 'ACTIVE' })).items;
  const spec = [
    { key: 'code', label: t('testing.fields.code'), required: true, readonly: Boolean(test), dir: 'ltr' },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('TEST') },
    { key: 'titleEn', label: t('testing.fields.titleEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'titleAr', label: t('testing.fields.titleAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'modelId', label: t('testing.fields.model'), type: 'select', required: true, options: listOptions(lookupList('models'), { withCode: true }) },
    { key: 'departmentId', label: t('fields.department'), type: 'select', required: true, options: listOptions(lookupList('departments')) },
    { key: 'testType', label: t('testing.fields.type'), type: 'select', required: true, options: ['INTERNAL', 'EXTERNAL'].map((x) => ({ value: x, label: t(`testing.types.${x}`) })) },
    { key: 'testDate', label: t('testing.fields.date'), type: 'date', required: true },
    { key: 'siteId', label: t('testing.fields.site'), type: 'select', options: listOptions(lookupList('sites')) },
    { key: 'unitId', label: t('testing.fields.unit'), type: 'select', required: true, options: unitOptions() },
    { key: 'projectId', label: t('testing.fields.project'), type: 'select', options: projects.map((p) => ({ value: p.id, label: `${p.code} · ${name(p)}` })) },
    { key: 'score', label: t('testing.fields.score'), type: 'number', step: 1 },
    { key: 'resultEn', label: t('testing.fields.resultEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    { key: 'resultAr', label: t('testing.fields.resultAr'), type: 'textarea', dir: 'rtl', max: 2000 },
    // Scans: the capability deed and the live demonstration report for the inspection (each a versioned document).
    ...(canAttach() ? TEST_SLOTS.map((slot) => ({ key: TEST_FILE_KEYS[slot], label: t(`testing.slots.${slot}`), type: 'file',
      current: test && test.attachments ? test.attachments[slot] : null })) : []),
  ];
  const values = test ? { code: test.code, statusCode: test.status, titleEn: test.titleEn, titleAr: test.titleAr, modelId: test.model && test.model.id,
    departmentId: test.department && test.department.id, testType: test.testType, testDate: test.testDate, siteId: test.site && test.site.id, unitId: test.unit && test.unit.id,
    projectId: test.project && test.project.id, score: test.score, resultEn: test.resultEn, resultAr: test.resultAr }
    : { code: codes.test, statusCode: 'PLANNED', testType: 'INTERNAL' };
  formDialog({ title: test ? t('testing.editTitle', { code: test.code }) : t('testing.newTitle'), spec, values, withReason: Boolean(test),
    submit: async (data) => {
      const files = takeFiles(data, TEST_FILE_KEYS);
      const saved = test ? await api.patch(`/tests/${test.id}`, { ...diff(values, data), version: test.version }) : await api.post('/tests', data);
      await attachAll('TEST_EVENT', saved.id, files);
      return saved;
    }, onSaved });
}

const TEST_SLOTS = ['CAPABILITY_DEED', 'LIVE_DEMO_REPORT'];
const TEST_FILE_KEYS = { CAPABILITY_DEED: 'fileDeed', LIVE_DEMO_REPORT: 'fileLiveDemo' };
const MAINT_FILE_KEYS = { INVESTIGATION: 'fileInvestigation' };
// The chosen files of a form, by slot (taken out of the record's own values; too large files refused first).
function takeFiles(data, keys) {
  const files = Object.fromEntries(Object.entries(keys).map(([slot, key]) => [slot, data[key]]));
  for (const key of Object.values(keys)) delete data[key];
  checkFiles(files);
  return files;
}

// ---------------------------------------------------------------- maintenance
async function maintenance(container) {
  const body = h('div');
  container.append(body);
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/maintenance', { department: state.department || undefined }); } catch (e) { replace(body, errorBox(e, load)); return; }
    const editable = canEdit('edit.maintenance');
    const changeable = canChange('edit.maintenance');
    const k = d.kpis;
    const open = d.items.filter((m) => !['COMPLETED', 'CANCELLED'].includes(m.status));
    replace(body,
      head(t('maintenance.title'), null, editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => maintenanceForm(null, load) }, icon('plus'), t('maintenance.add')) : null),
      h('div', { class: 'kpis' },
        kpiTile({ label: t('maintenance.kpi.active'), value: formatCount(k.active), tone: 'amber' }),
        kpiTile({ label: t('maintenance.kpi.overdue'), value: formatCount(k.overdue), tone: k.overdue ? 'red' : undefined }),
        kpiTile({ label: t('maintenance.kpi.partsShortage'), value: formatCount(k.partsShortage), tone: k.partsShortage ? 'red' : undefined }),
        kpiTile({ label: t('maintenance.kpi.awaitingParts'), value: formatCount(k.awaitingParts) }),
        kpiTile({ label: t('maintenance.kpi.completed'), value: formatCount(k.completed), tone: 'green' }),
        kpiTile({ label: t('maintenance.kpi.avgDuration'), value: k.avgDuration === null ? t('common.none') : formatCount(k.avgDuration) }),
        kpiTile({ label: t('maintenance.kpi.downtimeDays'), value: formatCount(k.downtimeDays) }),
        kpiTile({ label: t('maintenance.kpi.cost'), value: formatMoney(k.cost), money: true })),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-2' },
        card(t('maintenance.progress'), h('ul', { class: 'attention' }, open.map((m) => h('li', { class: m.overdue ? '' : 'amber' },
          h('div', { class: 'card-head', style: 'margin:0' }, h('span', {}, h('a', { href: `/assets/${m.asset.id}`, class: 'mono', text: m.asset.code }), ` · ${refName(m.model)} `, statusBadge('MAINTENANCE', m.status)),
            h('span', { class: 'mono small', text: formatPercent(m.progressPct) })),
          h('div', { class: 'small', text: name(m, 'title') }),
          h('div', { class: 'muted small', text: `${t('maintenance.fields.expected')} ${formatDate(m.expectedEndDate)}${m.overdue ? ` · ${t('maintenance.fields.overdue')} ${m.daysOverdue}` : ''}${m.partsText ? ` · ${m.partsText}` : ''}` }),
          meter(m.progressPct))))),
        h('div', { class: 'stack' },
          card(t('maintenance.readinessByDept'), dataTable([
            { key: 'd', label: t('fields.department'), render: (r) => refName(r.department) },
            { key: 'o', label: t('fields.opReadiness'), num: true, render: (r) => formatPercent(r.operational) },
            { key: 't', label: t('fields.techReadiness'), num: true, render: (r) => formatPercent(r.technical) },
            { key: 'm', label: t('fields.missionReadiness'), num: true, render: (r) => formatPercent(r.mission) },
            { key: 'mm', label: t('fields.maintReadiness'), num: true, render: (r) => formatPercent(r.maintenance) },
            { key: 'n', label: t('fields.assets'), num: true, render: (r) => formatCount(r.assets) },
          ], d.readinessByDepartment)),
          card(t('maintenance.byCategory'), h('div', {}, barRows(d.byCategory.map((c) => ({ label: c.category, parts: statuses('MAINTENANCE').map((s) => ({ value: c[s.code] || 0, color: colorOf(s.color), label: name(s) })) }))),
            legend(statuses('MAINTENANCE').map((s) => ({ color: colorOf(s.color), label: name(s) }))))))),
      h('div', { class: 'section-label' }),
      dataTable([
        { key: 'code', label: t('maintenance.fields.code'), render: (m) => h('span', { class: 'mono', text: m.code }) },
        { key: 'asset', label: t('maintenance.fields.asset'), render: (m) => h('a', { href: `/assets/${m.asset.id}`, class: 'mono', text: m.asset.code }) },
        { key: 'model', label: t('fields.model'), render: (m) => refName(m.model) },
        { key: 'dept', label: t('fields.department'), render: (m) => refName(m.department) },
        { key: 'type', label: t('maintenance.fields.type'), render: (m) => t(`maintenance.types.${m.type}`) },
        { key: 'title', label: t('maintenance.fields.title'), render: (m) => name(m, 'title') },
        { key: 'status', label: t('fields.status'), render: (m) => statusBadge('MAINTENANCE', m.status) },
        { key: 'start', label: t('maintenance.fields.start'), render: (m) => formatDate(m.startDate) },
        { key: 'exp', label: t('maintenance.fields.expected'), render: (m) => h('span', { class: m.overdue ? 'badge c-red no-dot' : '', text: formatDate(m.expectedEndDate) }) },
        { key: 'act', label: t('maintenance.fields.actual'), render: (m) => formatDate(m.actualEndDate) },
        { key: 'prog', label: t('maintenance.fields.progress'), num: true, render: (m) => formatPercent(m.progressPct) },
        { key: 'parts', label: t('maintenance.fields.parts'), render: (m) => (m.partsShortage ? h('span', { class: 'badge c-red wrap', text: m.partsText || t('maintenance.fields.shortage') }) : null) },
        { key: 'cost', label: t('maintenance.fields.cost'), num: true, render: (m) => formatMoney(m.cost) },
        changeable ? { key: 'edit', label: '', render: (m) => editBtn(() => maintenanceForm(m, load)) } : null,
      ].filter(Boolean), d.items));
  }
  await load();
}

async function maintenanceForm(order, onSaved) {
  const codes = order ? null : await api.get('/operations/next-code');
  const assets = order ? [] : (await api.get('/assets', { all: true })).items;
  const spec = [
    { key: 'code', label: t('maintenance.fields.code'), required: true, readonly: Boolean(order), dir: 'ltr' },
    order ? null : { key: 'assetId', label: t('maintenance.fields.asset'), type: 'select', required: true, options: assets.map((a) => ({ value: a.id, label: `${a.code} · ${refName(a.model)}` })) },
    { key: 'maintType', label: t('maintenance.fields.type'), type: 'select', required: true, options: ['PREVENTIVE', 'CORRECTIVE', 'INSPECTION', 'UPGRADE'].map((x) => ({ value: x, label: t(`maintenance.types.${x}`) })) },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('MAINTENANCE') },
    { key: 'titleEn', label: t('maintenance.fields.titleEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'titleAr', label: t('maintenance.fields.titleAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'startDate', label: t('maintenance.fields.start'), type: 'date', required: true },
    { key: 'expectedEndDate', label: t('maintenance.fields.expected'), type: 'date' },
    { key: 'actualEndDate', label: t('maintenance.fields.actual'), type: 'date' },
    { key: 'progressPct', label: t('maintenance.fields.progress'), type: 'number', step: 1 },
    { key: 'cost', label: t('maintenance.fields.cost'), type: 'number' },
    { key: 'partsShortage', label: t('maintenance.fields.shortage'), type: 'bool' },
    { key: 'partsText', label: t('maintenance.fields.parts'), max: 500 },
    { key: 'performedBy', label: t('maintenance.fields.by'), max: 160 },
    { key: 'entryReasonAr', label: t('capMaint.fields.reasonAr'), type: 'textarea', dir: 'rtl', max: 2000 },
    { key: 'entryReasonEn', label: t('capMaint.fields.reasonEn'), type: 'textarea', dir: 'ltr', max: 2000 },
    canAttach() ? { key: 'fileInvestigation', label: t('capMaint.slots.INVESTIGATION'), type: 'file',
      current: order && order.attachments ? order.attachments.INVESTIGATION : null } : null,
  ].filter(Boolean);
  const values = order ? { code: order.code, maintType: order.type, statusCode: order.status, titleEn: order.titleEn, titleAr: order.titleAr,
    startDate: order.startDate, expectedEndDate: order.expectedEndDate, actualEndDate: order.actualEndDate, progressPct: order.progressPct,
    cost: order.cost, partsShortage: order.partsShortage, partsText: order.partsText, performedBy: order.performedBy,
    entryReasonEn: order.entryReasonEn, entryReasonAr: order.entryReasonAr }
    : { code: codes.maintenance, maintType: 'CORRECTIVE', statusCode: 'PLANNED', progressPct: 0, partsShortage: false };
  formDialog({ title: order ? t('maintenance.editTitle', { code: order.code }) : t('maintenance.newTitle'), spec, values, withReason: Boolean(order),
    submit: async (data) => {
      const files = takeFiles(data, MAINT_FILE_KEYS);
      const saved = order ? await api.patch(`/maintenance/${order.id}`, { ...diff(values, data), version: order.version })
        : await api.post('/maintenance', { ...data, partsShortage: Boolean(data.partsShortage) });
      await attachAll('MAINTENANCE_ORDER', saved.id, files);
      return saved;
    }, onSaved });
}

// ---------------------------------------------------------------- capability maintenance
// Maintenance > Capability maintenance: why each capability entered maintenance, and the investigation board's scan.
async function capabilityMaintenance(container, ctx) {
  const body = h('div');
  container.append(body);
  let scope = (ctx && ctx.query.show) || 'open';
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/maintenance', { department: state.department || undefined }); } catch (e) { replace(body, errorBox(e, load)); return; }
    const changeable = canChange('edit.maintenance');  // the reason of an order that exists
    const isOpen = (m) => !['COMPLETED', 'CANCELLED'].includes(m.status);
    const rows = scope === 'all' ? d.items : d.items.filter(isOpen);
    const show = h('select', { class: 'select', 'aria-label': t('capMaint.show') },
      ['open', 'all'].map((v) => h('option', { value: v, text: t(`capMaint.showOptions.${v}`) })));
    show.value = scope;
    show.addEventListener('change', () => { scope = show.value; if (ctx) ctx.setQuery({ show: scope === 'open' ? undefined : scope }); load(); });
    replace(body,
      head(t('capMaint.title'), t('capMaint.subtitle'), h('div', { class: 'actions' }, show)),
      h('div', { class: 'kpis' },
        kpiTile({ label: t('capMaint.kpi.orders'), value: formatCount(rows.length) }),
        kpiTile({ label: t('capMaint.kpi.withReason'), value: formatCount(rows.filter((m) => m.entryReasonAr || m.entryReasonEn).length), tone: 'green' }),
        kpiTile({ label: t('capMaint.kpi.noReason'), value: formatCount(rows.filter((m) => !m.entryReasonAr && !m.entryReasonEn).length), tone: 'amber' }),
        kpiTile({ label: t('capMaint.kpi.withInvestigation'), value: formatCount(rows.filter((m) => m.attachments && m.attachments.INVESTIGATION).length) })),
      h('div', { class: 'section-label' }),
      dataTable([
        { key: 'code', label: t('maintenance.fields.code'), render: (m) => h('button', { type: 'button', class: 'btn btn-sm btn-ghost mono', text: m.code, onclick: () => showOrder(m, load) }) },
        { key: 'asset', label: t('maintenance.fields.asset'), render: (m) => h('a', { href: `/assets/${m.asset.id}`, class: 'mono', text: m.asset.code }) },
        { key: 'model', label: t('fields.model'), render: (m) => refName(m.model) },
        { key: 'type', label: t('maintenance.fields.type'), render: (m) => t(`maintenance.types.${m.type}`) },
        { key: 'status', label: t('fields.status'), render: (m) => statusBadge('MAINTENANCE', m.status) },
        { key: 'start', label: t('capMaint.fields.entered'), render: (m) => formatDate(m.startDate) },
        { key: 'reason', label: t('capMaint.fields.reason'), render: (m) => (m.entryReasonAr || m.entryReasonEn
          ? h('div', { class: 'reason-text', text: name(m, 'entryReason') }) : h('span', { class: 'muted small', text: t('capMaint.noReason') })) },
        { key: 'inv', label: t('capMaint.slots.INVESTIGATION'), render: (m) => slotMark(m.attachments && m.attachments.INVESTIGATION, t('capMaint.slots.INVESTIGATION')) },
        { key: 'open', label: '', render: (m) => h('div', { class: 'row-actions' },
          h('button', { type: 'button', class: 'btn btn-sm', onclick: () => showOrder(m, load) }, icon('file'), t('capMaint.details')),
          changeable ? h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('capMaint.editReason'), onclick: () => reasonForm(m, load) }, icon('edit')) : null) },
      ], rows, { empty: t('capMaint.empty') }));
  }
  await load();
}

function showOrder(order, onChanged) {
  const body = h('div');
  const modal = openModal({ title: `${order.code} · ${order.asset.code} · ${refName(order.model)}`, body, size: 'lg' });
  function draw(m) {
    replace(body,
      h('dl', { class: 'dl' },
        h('div', {}, h('dt', { text: t('maintenance.fields.title') }), h('dd', { text: name(m, 'title') })),
        h('div', {}, h('dt', { text: t('fields.status') }), h('dd', {}, statusBadge('MAINTENANCE', m.status))),
        h('div', {}, h('dt', { text: t('capMaint.fields.entered') }), h('dd', { text: formatDate(m.startDate) }))),
      card(t('capMaint.fields.reason'), m.entryReasonAr || m.entryReasonEn ? h('p', { class: 'reason-text', text: name(m, 'entryReason') })
        : h('p', { class: 'muted', text: t('capMaint.noReason') }),
      { actions: canChange('edit.maintenance') ? h('button', { type: 'button', class: 'btn btn-sm', onclick: () => { modal.close(true); reasonForm(m, onChanged); } }, icon('edit'), t('capMaint.editReason')) : null }),
      card(t('capMaint.slots.INVESTIGATION'), h('div', { class: 'slots' }, slotRow({
        entityType: 'MAINTENANCE_ORDER', entityId: m.id, docType: 'INVESTIGATION', label: t('capMaint.slots.INVESTIGATION'),
        current: m.attachments && m.attachments.INVESTIGATION,
        onChanged: async () => {
          onChanged();
          const d = await api.get('/maintenance', { asset: m.asset.id });
          const fresh = d.items.find((x) => x.id === m.id);
          if (fresh) draw(fresh);
        },
      }))));
  }
  draw(order);
}

function reasonForm(order, onSaved) {
  const values = { entryReasonAr: order.entryReasonAr, entryReasonEn: order.entryReasonEn };
  formDialog({
    title: t('capMaint.reasonTitle', { code: order.code }), size: 'md', values, withReason: true,
    spec: [
      { key: 'entryReasonAr', label: t('capMaint.fields.reasonAr'), type: 'textarea', dir: 'rtl', max: 2000, span: true },
      { key: 'entryReasonEn', label: t('capMaint.fields.reasonEn'), type: 'textarea', dir: 'ltr', max: 2000, span: true },
      canAttach() ? { key: 'fileInvestigation', label: t('capMaint.slots.INVESTIGATION'), type: 'file', span: true,
        current: order.attachments ? order.attachments.INVESTIGATION : null } : null,
    ].filter(Boolean),
    submit: async (data) => {
      const files = takeFiles(data, MAINT_FILE_KEYS);
      const saved = await api.patch(`/maintenance/${order.id}`, { ...diff(values, data), version: order.version });
      await attachAll('MAINTENANCE_ORDER', saved.id, files);
      return saved;
    },
    onSaved,
  });
}

// ---------------------------------------------------------------- AI
async function ai(container) {
  const body = h('div');
  container.append(body);
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/ai'); } catch (e) { replace(body, errorBox(e, load)); return; }
    const levelName = (n) => (n ? `L${n} · ${name(d.criteria[n - 1])}` : t('ai.noneLevel'));
    const matrix = h('div', { class: 'table-wrap' }, h('table', { class: 'data' },
      h('thead', {}, h('tr', {}, h('th', { text: t('fields.model') }), h('th', { text: t('ai.level') }),
        d.technologies.map((tech) => h('th', { class: 'vertical', title: name(tech), text: name(tech) })))),
      h('tbody', {}, d.models.map((m) => h('tr', {},
        h('td', {}, h('a', { href: `/models/${m.model.id}?tab=ai`, text: `${name(m.model)}` }), h('span', { class: 'muted small', text: ` ${m.category ? m.category.code : ''}` })),
        h('td', {}, h('span', { class: `badge ${m.level >= 4 ? 'c-purple' : m.level >= 2 ? 'c-blue' : 'c-grey'}`, text: `L${m.level}` })),
        d.technologies.map((tech) => h('td', { style: 'text-align:center', title: name(tech) }, m.supported.includes(tech.code) ? h('span', { style: 'color:var(--green)', text: '●' }) : h('span', { class: 'muted', text: '·' }))))))));
    const criteria = dataTable([
      { key: 'l', label: t('ai.level'), render: (c) => h('strong', { text: `L${c.level}` }) },
      { key: 'n', label: t('fields.nameEn'), render: (c) => name(c) },
      { key: 'd', label: t('common.details'), render: (c) => name(c, 'description') },
      { key: 'm', label: '', render: (c) => t('ai.minSupported', { n: c.minSupported }) },
      { key: 'r', label: '', render: (c) => (c.required.length ? t('ai.required', { list: c.required.map((code) => name(d.technologies.find((x) => x.code === code) || { nameEn: code })).join(', ') }) : null) },
    ], d.criteria);
    replace(body,
      head(t('ai.title')),
      card(t('ai.matrix'), matrix),
      h('div', { class: 'section-label' }),
      h('div', { class: 'grid grid-3' },
        h('div', { class: 'span-2' }, card(t('ai.criteria'), criteria, { actions: isAdmin() ? h('span', { class: 'muted small', text: levelName(0) }) : null })),
        h('div', { class: 'stack' },
          card(t('ai.byDepartment'), barRows(d.byDepartment.map((r) => ({ label: name(r.department), parts: [{ value: r.average, color: 'var(--chart-5)', label: '' }], total: formatNumber(r.average, 1) })), 5)),
          card(t('ai.byCategory'), barRows(d.byCategory.map((r) => ({ label: r.category.code, parts: [{ value: r.average, color: 'var(--chart-5)', label: '' }], total: formatNumber(r.average, 1) })), 5)))),
      h('div', { class: 'section-label' }),
      card(t('ai.opportunities'), developmentTable(d.opportunities, null)));
  }
  await load();
}

export async function modelAiPanel(model, onChanged) {
  const d = await api.get(`/models/${model.id}/ai`);
  const editable = canChange('edit.models');  // the model exists: its AI functions are a change
  const levelBox = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { text: t('ai.levelOf', { n: d.level }) })),
    h('h3', { text: t('ai.trace') }),
    dataTable([
      { key: 'l', label: t('ai.level'), render: (x) => `L${x.level} · ${name(x)}` },
      { key: 'm', label: '', render: (x) => h('span', { class: `badge ${x.met ? 'c-green' : 'c-grey'}`, text: x.met ? t('ai.met') : t('ai.missing') }) },
      { key: 'd', label: '', render: (x) => `${x.supported}/${x.minSupported}${x.missing.length ? ` · ${t('ai.missing')}: ${x.missing.join(', ')}` : ''}` },
    ], d.trace));
  const techBox = h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', { text: t('ai.matrix') }),
    editable ? h('button', { type: 'button', class: 'btn btn-sm', onclick: () => {
      formDialog({ title: t('ai.editTech'), size: 'md', values: { technologies: d.technologies.filter((x) => x.supported).map((x) => x.code) },
        spec: [{ key: 'technologies', label: t('ai.supported'), type: 'checks', span: true, options: d.technologies.map((x) => ({ value: x.code, label: name(x) })) }],
        withReason: true, submit: (data) => api.put(`/models/${model.id}/ai`, data), onSaved: onChanged });
    } }, icon('edit'), t('ai.editTech')) : null),
  h('ul', { class: 'status-list' }, d.technologies.map((x) => h('li', {}, h('span', { class: 'actions' },
    h('span', { class: `badge ${x.supported ? 'c-green' : 'c-grey'}`, text: x.supported ? t('ai.supported') : t('ai.notSupported') }), name(x))))));
  return h('div', { class: 'grid grid-2' }, levelBox, techBox);
}

// ---------------------------------------------------------------- development
function developmentTable(items, onEdit) {
  return dataTable([
    { key: 'code', label: t('development.fields.code'), render: (o) => h('span', { class: 'mono', text: o.code }) },
    { key: 'model', label: t('development.fields.model'), render: (o) => (o.model ? h('a', { href: `/models/${o.model.id}`, text: name(o.model) }) : null) },
    { key: 'type', label: t('development.fields.type'), render: (o) => t(`development.types.${o.type}`) },
    { key: 'title', label: t('development.fields.title'), render: (o) => name(o, 'title') },
    { key: 'benefit', label: t('development.fields.benefit'), render: (o) => name(o, 'benefit') },
    { key: 'status', label: t('fields.status'), render: (o) => statusBadge('DEVELOPMENT', o.status) },
    { key: 'cx', label: t('development.fields.complexity'), render: (o) => t(`development.complexity.${o.complexity}`) },
    { key: 'cost', label: t('development.fields.cost'), num: true, render: (o) => formatMoney(o.estimatedCost) },
    { key: 'months', label: t('development.fields.months'), num: true, render: (o) => (o.durationMonths === null ? null : String(o.durationMonths)) },
    { key: 'priority', label: t('development.fields.priority'), render: (o) => priorityBadge(o.priority) },
    { key: 'project', label: t('development.fields.project'), render: (o) => (o.project ? h('a', { href: `/projects/${o.project.id}`, class: 'mono', text: o.project.code }) : null) },
    onEdit ? { key: 'edit', label: '', render: (o) => editBtn(() => onEdit(o)) } : null,
  ].filter(Boolean), items);
}

async function development(container) {
  const body = h('div');
  container.append(body);
  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/development'); } catch (e) { replace(body, errorBox(e, load)); return; }
    const editable = canEdit('edit.models');
    const changeable = canChange('edit.models');
    const total = d.items.length;
    replace(body,
      head(t('development.title'), null, editable ? h('button', { type: 'button', class: 'btn btn-primary', onclick: () => developmentForm(null, load) }, icon('plus'), t('development.add')) : null),
      h('div', { class: 'grid grid-2' },
        card(t('development.byStatus'), barRows(d.byStatus.map((s) => { const def = statusDef('DEVELOPMENT', s.status); return { label: def ? name(def) : s.status, parts: [{ value: s.count, color: colorOf(def && def.color), label: '' }] }; }), total)),
        card(t('development.byType'), barRows(d.byType.map((s) => ({ label: t(`development.types.${s.type}`), parts: [{ value: s.count, color: 'var(--chart-1)', label: '' }] })), total))),
      h('div', { class: 'section-label' }),
      developmentTable(d.items, changeable ? (o) => developmentForm(o, load) : null));
  }
  await load();
}

async function developmentForm(opp, onSaved) {
  const codes = opp ? null : await api.get('/operations/next-code');
  const projects = (await api.get('/projects')).items;
  const spec = [
    { key: 'code', label: t('development.fields.code'), required: true, readonly: Boolean(opp), dir: 'ltr' },
    { key: 'modelId', label: t('development.fields.model'), type: 'select', required: true, options: listOptions(lookupList('models'), { withCode: true }) },
    { key: 'devType', label: t('development.fields.type'), type: 'select', required: true, options: Object.keys(t('development.types')).map((x) => ({ value: x, label: t(`development.types.${x}`) })) },
    { key: 'statusCode', label: t('fields.status'), type: 'select', required: true, options: statusOptions('DEVELOPMENT') },
    { key: 'titleEn', label: t('development.fields.titleEn'), required: true, max: 200, dir: 'ltr' },
    { key: 'titleAr', label: t('development.fields.titleAr'), required: true, max: 200, dir: 'rtl' },
    { key: 'benefitEn', label: t('development.fields.benefitEn'), max: 500, dir: 'ltr' },
    { key: 'benefitAr', label: t('development.fields.benefitAr'), max: 500, dir: 'rtl' },
    { key: 'complexity', label: t('development.fields.complexity'), type: 'select', required: true, options: ['LOW', 'MEDIUM', 'HIGH'].map((x) => ({ value: x, label: t(`development.complexity.${x}`) })) },
    { key: 'priority', label: t('development.fields.priority'), type: 'select', required: true, options: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((x) => ({ value: x, label: t(`priority.${x}`) })) },
    { key: 'estimatedCost', label: t('development.fields.cost'), type: 'number' },
    { key: 'durationMonths', label: t('development.fields.months'), type: 'number', step: 1 },
    { key: 'projectId', label: t('development.fields.project'), type: 'select', options: projects.map((p) => ({ value: p.id, label: `${p.code} · ${name(p)}` })) },
  ];
  const values = opp ? { code: opp.code, modelId: opp.model && opp.model.id, devType: opp.type, statusCode: opp.status, titleEn: opp.titleEn,
    titleAr: opp.titleAr, benefitEn: opp.benefitEn, benefitAr: opp.benefitAr, complexity: opp.complexity, priority: opp.priority,
    estimatedCost: opp.estimatedCost, durationMonths: opp.durationMonths, projectId: opp.project && opp.project.id }
    : { code: codes.development, devType: 'AI', statusCode: 'PROPOSED', complexity: 'MEDIUM', priority: 'MEDIUM' };
  formDialog({ title: opp ? t('development.editTitle', { code: opp.code }) : t('development.newTitle'), spec, values, withReason: Boolean(opp),
    submit: (data) => (opp ? api.patch(`/development/${opp.id}`, { ...diff(values, data), version: opp.version }) : api.post('/development', data)), onSaved });
}

// ---------------------------------------------------------------- decision support
async function decision(container) {
  const body = h('div');
  container.append(head(t('decision.title'), t('decision.subtitle')), body);
  replace(body, loadingBox());
  try {
    const d = await api.get('/decision-support');
    const tone = { RED: 'var(--red)', AMBER: 'var(--chart-3)', BLUE: 'var(--chart-1)', GREEN: 'var(--green)' };
    replace(body, h('div', { class: 'grid grid-3' }, d.panels.map((p) => card(t(`decision.panels.${p.key}`), h('div', {},
      h('div', { class: 'kpi-value', text: formatCount(p.count) }), h('div', { class: 'muted small', text: t('decision.records', { n: p.count }) }),
      h('ul', { class: 'attention', style: 'margin-top:8px' }, p.items.slice(0, 6).map((i) => h('li', { style: `border-inline-start-color:${tone[i.tone] || tone.RED}` },
        h('a', { href: i.link, text: name(i, 'text') }), i.subEn ? h('div', { class: 'muted small', text: name(i, 'sub') }) : null)))),
    { foot: `${t('common.basis')} ${name(p, 'basis')}` }))));
  } catch (e) { replace(body, errorBox(e)); }
}
