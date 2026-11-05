// Reports and analytics: the report catalogue (about 130 predefined reports), the report view with its header
// (generation details, filters, classification), exports (PDF via print, Excel, CSV, PowerPoint), the custom report
// builder with saved templates, scheduled reports and the run history.
import { api, download } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { language } from '../lib/i18n.js';
import { can } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatDate, formatDateTime, formatMoney, formatNumber } from '../lib/format.js';
import { barRows, card, dataTable, errorBox, field, loadingBox, selectEl, tabs, toast } from '../components/ui.js';
import { formDialog } from './forms.js';

const LANGS = ['EN', 'AR', 'BILINGUAL'];

function cell(value, kind) {
  if (value === null || value === undefined || value === '') return t('common.none');
  if (kind === 'percent') return `${formatNumber(value, 0)}%`;
  if (kind === 'money') return formatMoney(value);
  if (kind === 'date') return formatDate(value);
  if (kind === 'number' && typeof value === 'number') return formatNumber(value, 1);
  // Record codes (RSK-007, PRJ-011, UAV-001) never break across lines.
  if (CODE_RE.test(value)) return h('span', { class: 'mono', text: value });
  return String(value);
}
const CODE_RE = /^[A-Z]{2,5}-\d+$/;

// The report as a printable document: header (title, generation details, filters, classification) and its sections.
export function reportView(result, lang) {
  const hd = result.header;
  const title = lang === 'AR' ? result.titleAr : lang === 'BILINGUAL' ? `${result.titleEn} / ${result.titleAr}` : result.titleEn;
  const filters = Object.entries(hd.filters || {}).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(' · ');
  const doc = h('article', { class: 'report-doc', dir: lang === 'AR' ? 'rtl' : 'ltr', lang: lang === 'AR' ? 'ar' : 'en' },
    h('header', { class: 'report-head' },
      h('div', { class: 'actions', style: 'justify-content:space-between' },
        h('div', { class: 'actions' }, h('img', { src: '/assets/icons/favicon.svg', alt: '', width: 36, height: 36 }),
          h('div', {}, h('strong', { text: t('app.name') }), h('div', { class: 'muted small', text: t('app.subtitle') }))),
        h('span', { class: 'badge c-amber no-dot', text: hd.classification })),
      h('h2', { class: 'report-title', text: title }),
      h('div', { class: 'report-meta small' },
        h('span', { text: `${t('reports.header.generated')}: ${formatDateTime(hd.generatedAt)}` }),
        h('span', { text: `${t('reports.header.by')}: ${hd.generatedBy}` }),
        h('span', { text: `${t('reports.header.role')}: ${hd.role}` }),
        h('span', { text: `${t('reports.header.asOf')}: ${formatDate(hd.asOf)}` }),
        h('span', { text: `${t('reports.header.language')}: ${t(`reports.lang.${hd.language}`)}` })),
      h('div', { class: 'notice small', text: `${t('reports.header.filters')}: ${filters || t('reports.header.none')}` })));
  for (const s of result.sections) {
    if (s.kind === 'kpis') {
      doc.append(h('section', { class: 'report-section' }, s.title ? h('h3', { text: s.title }) : null,
        h('div', { class: 'kpis' }, s.items.map((i) => h('div', { class: 'kpi static' }, h('span', { class: 'kpi-label', text: i.label }),
          h('span', { class: 'kpi-value', text: formatNumber(i.value, 1) }),
          i.trend ? h('span', { class: 'kpi-trend', text: `${formatNumber(i.trend.m ?? 0, 0)} ${t('common.sinceMonth')}` }) : null)))));
    } else if (s.kind === 'table') {
      doc.append(h('section', { class: 'report-section' }, h('h3', { text: s.title || '' }),
        dataTable(s.columns.map((c) => ({ key: c.key, label: c.label, num: ['number', 'percent', 'money'].includes(c.kind), render: (r) => cell(r[c.key], c.kind) })), s.rows)));
    } else if (s.kind === 'bar') {
      doc.append(h('section', { class: 'report-section' }, h('h3', { text: s.title || '' }),
        barRows(s.items.map((i) => ({ label: i.label, parts: [{ value: Number(i.value) || 0, color: 'var(--chart-1)', label: i.label }], total: formatNumber(i.value, 1) })))));
    } else if (s.kind === 'list') {
      doc.append(h('section', { class: 'report-section' }, h('h3', { text: s.title || '' }), s.basis ? h('p', { class: 'muted small', text: s.basis }) : null,
        s.items.length ? h('ul', { class: 'attention' }, s.items.map((i) => h('li', { text: i }))) : h('p', { class: 'muted', text: t('common.none') })));
    }
  }
  return doc;
}

function exportBar(key, lang, onPdf) {
  const btn = (fmt) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => download(`/reports/${encodeURIComponent(key)}/export`, { format: fmt, lang }).catch((e) => toast(e.message, true)) }, icon('download'), t(`reports.export.${fmt}`));
  return h('div', { class: 'actions no-print' },
    h('button', { type: 'button', class: 'btn btn-sm', onclick: onPdf }, icon('download'), t('reports.export.PDF')),
    can('export') ? [btn('XLSX'), btn('CSV'), btn('PPTX')] : null,
    h('button', { type: 'button', class: 'btn btn-sm', onclick: onPdf }, icon('printer'), t('reports.export.PRINT')));
}

export async function render(container, ctx) {
  let tab = ctx.query.tab || 'catalogue';
  let lang = ctx.query.lang || (language() === 'ar' ? 'AR' : 'EN');
  let selected = ctx.query.report || null;
  let filter = '';
  const head = h('div', { class: 'page-head no-print' });
  const bar = h('div', { class: 'no-print' });
  const body = h('div');
  container.append(head, bar, body);
  let data;
  try { data = await api.get('/reports'); } catch (e) { replace(body, errorBox(e)); return; }
  replace(head, h('div', {}, h('h1', { tabindex: '-1', text: t('reports.title') }), h('div', { class: 'page-sub', text: t('reports.subtitle', { n: data.total }) })));
  const save = () => ctx.setQuery({ tab, report: selected || undefined, lang });
  const visibleTabs = ['catalogue', can('reports.build') ? 'builder' : null, can('reports.schedule') ? 'schedules' : null, 'history'].filter(Boolean);

  async function draw() {
    replace(bar, tabs(visibleTabs.map((k) => ({ key: k, label: t(`reports.tabs.${k}`) })), tab, (k) => { tab = k; save(); draw(); }));
    if (tab === 'catalogue') return catalogue();
    if (tab === 'builder') return builder();
    if (tab === 'schedules') return schedules();
    return history();
  }

  function langSwitch(onChange) {
    return h('div', { class: 'segmented no-print' }, LANGS.map((l) => h('button', { type: 'button', 'aria-pressed': lang === l ? 'true' : 'false', text: t(`reports.lang.${l}`), onclick: () => { lang = l; save(); onChange(); } })));
  }

  async function catalogue() {
    const list = h('nav', { class: 'card report-list no-print' });
    const view = h('div');
    replace(body, h('div', { class: 'report-layout' }, list, view));
    const search = h('input', { class: 'input', type: 'search', placeholder: t('reports.searchReports'), value: filter });
    search.addEventListener('input', () => { filter = search.value.trim().toLowerCase(); drawList(); });
    function drawList() {
      const groups = data.categories.map((c) => {
        const items = data.items.filter((r) => r.category === c.key && (!filter || `${r.titleEn} ${r.titleAr}`.toLowerCase().includes(filter)));
        if (!items.length) return null;
        return h('details', { open: !filter && c.key !== 'executive' ? undefined : true },
          h('summary', { class: 'small', text: `${name(c, 'title')} (${items.length})` }),
          h('ul', { class: 'status-list' }, items.map((r) => h('li', {}, h('button', { type: 'button', 'aria-current': selected === r.key ? 'true' : undefined,
            style: selected === r.key ? 'background:var(--gold-100)' : '', onclick: () => { selected = r.key; save(); drawList(); show(); } },
          h('span', {}), h('span', { text: name(r, 'title') }), h('span'))))));
      });
      const templates = data.templates.length ? h('details', { open: true }, h('summary', { class: 'small', text: t('reports.builder.templates') }),
        h('ul', { class: 'status-list' }, data.templates.map((tpl) => h('li', {}, h('button', { type: 'button', onclick: () => { selected = `template-${tpl.id}`; save(); show(); } },
          h('span'), h('span', { text: tpl.name }), h('span')))))) : null;
      replace(list, search, templates, groups);
    }
    async function show() {
      if (!selected) { replace(view, card(null, h('p', { class: 'muted', text: t('reports.choose') }))); return; }
      replace(view, loadingBox());
      try {
        const result = await api.get(`/reports/${encodeURIComponent(selected)}`, { lang });
        replace(view, h('div', { class: 'toolbar no-print' }, langSwitch(show), exportBar(selected, lang, () => window.print())), card(null, reportView(result, lang)));
      } catch (e) { replace(view, errorBox(e, show)); }
    }
    drawList();
    show();
  }

  function builder() {
    const datasets = data.datasets;
    const dsSel = selectEl(Object.entries(datasets).map(([k, d]) => ({ value: k, label: name(d, 'title') })), 'assets');
    const fieldsBox = h('div');
    const out = h('div');
    let state = { dataset: 'assets', columns: null, group: '', filterField: '', filterValue: '', sort: '', chart: 'table' };
    function controls() {
      const ds = datasets[state.dataset];
      const fieldOpts = ds.fields.map((f) => ({ value: f.key, label: language() === 'ar' ? f.labelAr : f.labelEn }));
      const cols = h('div', { class: 'checks' }, ds.fields.map((f) => h('label', {}, h('input', { type: 'checkbox', value: f.key,
        checked: (!state.columns || state.columns.includes(f.key)) || undefined, onchange: () => { state.columns = [...cols.querySelectorAll('input:checked')].map((i) => i.value); } }),
      language() === 'ar' ? f.labelAr : f.labelEn)));
      const group = selectEl(ds.fields.filter((f) => f.group).map((f) => ({ value: f.key, label: language() === 'ar' ? f.labelAr : f.labelEn })), state.group, { includeEmpty: true, emptyLabel: t('reports.builder.none') });
      group.addEventListener('change', () => { state.group = group.value; });
      const ff = selectEl(fieldOpts, state.filterField, { includeEmpty: true, emptyLabel: t('common.none') });
      ff.addEventListener('change', () => { state.filterField = ff.value; });
      const fv = h('input', { class: 'input', value: state.filterValue });
      fv.addEventListener('input', () => { state.filterValue = fv.value; });
      const sort = selectEl(fieldOpts, state.sort, { includeEmpty: true, emptyLabel: t('common.none') });
      sort.addEventListener('change', () => { state.sort = sort.value; });
      replace(fieldsBox, h('div', { class: 'form-grid' }, field(t('reports.builder.group'), group), field(t('reports.builder.filter'), ff),
        field(t('reports.builder.value'), fv), field(t('reports.builder.sort'), sort)),
      h('div', { class: 'section-label', text: t('reports.builder.columns') }), cols);
    }
    dsSel.addEventListener('change', () => { state = { ...state, dataset: dsSel.value, columns: null, group: '', filterField: '', sort: '' }; controls(); });
    const definition = () => ({ dataset: state.dataset, columns: state.group ? undefined : state.columns || undefined, group: state.group || undefined,
      filters: state.filterField ? { [state.filterField]: state.filterValue } : undefined, sort: state.sort || undefined });
    const run = async () => {
      replace(out, loadingBox());
      try { const result = await api.post('/reports/custom', { definition: definition(), lang }); replace(out, card(null, reportView(result, lang))); } catch (e) { replace(out, errorBox(e)); }
    };
    const saveTpl = () => formDialog({ title: t('reports.builder.save'), size: 'md', values: { shared: false },
      spec: [{ key: 'name', label: t('reports.builder.templateName'), required: true, max: 120 }, { key: 'shared', label: t('reports.builder.shared'), type: 'bool' }],
      submit: (d) => api.post('/report-templates', { name: d.name, shared: Boolean(d.shared), definition: definition() }),
      onSaved: async () => { data = await api.get('/reports'); } });
    replace(body, card(null, h('div', {}, h('div', { class: 'form-grid' }, field(t('reports.builder.dataset'), dsSel)), fieldsBox,
      h('div', { class: 'actions', style: 'margin-top:12px' }, langSwitch(() => {}),
        h('button', { type: 'button', class: 'btn btn-primary', onclick: run, text: t('reports.builder.run') }),
        h('button', { type: 'button', class: 'btn', onclick: saveTpl, text: t('reports.builder.save') })))), h('div', { class: 'section-label' }), out);
    controls();
  }

  async function schedules() {
    replace(body, loadingBox());
    try {
      const d = await api.get('/report-schedules');
      const reportOptions = data.items.map((r) => ({ value: r.key, label: name(r, 'title') }));
      const open = (s) => formDialog({ title: s ? s.name : t('reports.schedules.newTitle'), size: 'md', withReason: Boolean(s),
        values: s ? { name: s.name, reportKey: s.reportKey, frequency: s.frequency, language: s.language, format: s.format, runTime: s.runTime,
          outputFolder: s.outputFolder, nextRunDate: s.nextRunDate, active: s.active } : { frequency: 'WEEKLY', language: 'EN', format: 'XLSX', runTime: '07:00', outputFolder: 'Reports', active: true },
        spec: [{ key: 'name', label: t('reports.schedules.name'), required: true, max: 120 },
          { key: 'reportKey', label: t('reports.schedules.report'), type: 'select', required: true, options: reportOptions },
          { key: 'frequency', label: t('reports.schedules.frequency'), type: 'select', required: true, options: ['DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY'].map((f) => ({ value: f, label: t(`reports.schedules.freq.${f}`) })) },
          { key: 'language', label: t('reports.schedules.language'), type: 'select', required: true, options: LANGS.map((l) => ({ value: l, label: t(`reports.lang.${l}`) })) },
          { key: 'format', label: t('reports.schedules.format'), type: 'select', required: true, options: ['XLSX', 'CSV', 'PPTX', 'HTML'].map((f) => ({ value: f, label: f })) },
          { key: 'runTime', label: t('reports.schedules.time'), required: true, max: 5, dir: 'ltr' },
          { key: 'outputFolder', label: t('reports.schedules.folder'), required: true, max: 80 },
          { key: 'nextRunDate', label: t('reports.schedules.next'), type: 'date' },
          { key: 'active', label: t('reports.schedules.active'), type: 'bool' }],
        submit: (v) => {
          const payload = { ...v, active: v.active !== false };
          return s ? api.patch(`/report-schedules/${s.id}`, { ...payload, version: s.version }) : api.post('/report-schedules', payload);
        },
        onSaved: schedules });
      replace(body, h('div', { class: 'toolbar' }, h('p', { class: 'muted small', text: t('reports.schedules.note') }),
        h('button', { type: 'button', class: 'btn btn-primary', onclick: () => open(null) }, icon('plus'), t('reports.schedules.add'))),
      dataTable([
        { key: 'n', label: t('reports.schedules.name'), render: (s) => s.name },
        { key: 'r', label: t('reports.schedules.report'), render: (s) => (s.report ? (language() === 'ar' ? s.report.ar : s.report.en) : s.reportKey) },
        { key: 'f', label: t('reports.schedules.frequency'), render: (s) => t(`reports.schedules.freq.${s.frequency}`) },
        { key: 'l', label: t('reports.schedules.language'), render: (s) => t(`reports.lang.${s.language}`) },
        { key: 'fmt', label: t('reports.schedules.format'), render: (s) => s.format },
        { key: 't', label: t('reports.schedules.time'), render: (s) => h('span', { class: 'mono', text: s.runTime }) },
        { key: 'o', label: t('reports.schedules.folder'), render: (s) => s.outputFolder },
        { key: 'nx', label: t('reports.schedules.next'), render: (s) => formatDate(s.nextRunDate) },
        { key: 'a', label: t('reports.schedules.active'), render: (s) => h('span', { class: `badge ${s.active ? 'c-green' : 'c-grey'}`, text: s.active ? t('common.yes') : t('common.no') }) },
        { key: 'e', label: '', render: (s) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => open(s) }, icon('edit')) },
      ], d.items));
    } catch (e) { replace(body, errorBox(e, schedules)); }
  }

  async function history() {
    replace(body, loadingBox());
    try {
      const d = await api.get('/reports/history');
      replace(body, dataTable([
        { key: 'w', label: t('reports.history.when'), render: (r) => formatDateTime(r.runAt) },
        { key: 'r', label: t('reports.history.report'), render: (r) => r.title },
        { key: 'b', label: t('reports.history.by'), render: (r) => r.by },
        { key: 'l', label: t('reports.history.language'), render: (r) => t(`reports.lang.${r.language}`) },
        { key: 'f', label: t('reports.history.format'), render: (r) => r.format },
        { key: 'n', label: t('reports.history.rows'), num: true, render: (r) => String(r.rows) },
        { key: 's', label: t('reports.history.scheduled'), render: (r) => (r.scheduled ? t('common.yes') : '') },
        { key: 'file', label: t('reports.history.file'), render: (r) => (r.hasFile ? h('button', { type: 'button', class: 'btn btn-sm',
          onclick: () => download(`/reports/history/${r.id}/file`).catch((e) => toast(e.message, true)) }, icon('download'), t('reports.history.download')) : null) },
      ], d.items));
    } catch (e) { replace(body, errorBox(e, history)); }
  }

  await draw();
}
