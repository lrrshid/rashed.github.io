// Small shared widgets: badges, KPI tiles, tables, pager, rings, meters, bars, tabs, form fields, toasts, history.
import { h, icon, replace } from '../lib/dom.js';
import { formatCount, formatDate, formatDateTime, formatNumber, formatPercent } from '../lib/format.js';
import { name, t } from '../labels.js';
import { findById, statusDef } from '../lib/state.js';

export function badge(color, text, extra = '') {
  return h('span', { class: `badge c-${color || 'grey'} ${extra}`, text });
}

export function statusBadge(domain, code) {
  if (!code) return h('span', { class: 'muted', text: t('common.none') });
  const def = statusDef(domain, code);
  return badge(def ? def.color : 'grey', def ? name(def) : code);
}

const PRIORITY_COLORS = { CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'amber', LOW: 'grey' };
export function priorityBadge(priority) {
  return badge(PRIORITY_COLORS[priority] || 'grey', t(`priority.${priority}`));
}

export function ragDot(rag) {
  return h('span', { class: `rag rag-${rag || 'GREY'}`, text: t(`rag.${rag || 'GREY'}`) });
}

export function refName(ref) { return ref ? name(ref) : t('common.none'); }
export function lookupName(list, id) { return refName(findById(list, id)); }

// A KPI tile. trend: {m, q, y} deltas (numbers or null); lowerIsBetter flips the colours.
export function kpiTile({ label, value, tone, trend, onClick, money = false, lowerIsBetter = false, title }) {
  const el = h(onClick ? 'button' : 'div', {
    type: onClick ? 'button' : undefined, class: `kpi ${tone ? `tone-${tone}` : ''} ${onClick ? '' : 'static'}`, title,
  },
  h('span', { class: 'kpi-label', text: label }),
  h('span', { class: `kpi-value ${money ? 'money' : ''}`, text: value }));
  if (trend) {
    const part = (delta, unit) => {
      if (delta === null || delta === undefined) return h('span', { text: `■ — ${unit}` });
      const dir = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
      const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '■';
      return h('span', { class: `trend-${dir} ${lowerIsBetter ? 'trend-bad' : ''}`, text: `${arrow} ${formatNumber(Math.abs(delta), 0)} ${unit}` });
    };
    el.append(h('span', { class: 'kpi-trend' }, part(trend.m, t('common.sinceMonth')), part(trend.q, t('common.sinceQuarter')),
      part(trend.y, t('common.sinceYear'))));
  }
  if (onClick) el.addEventListener('click', onClick);
  return el;
}

// columns: [{ key, label, render(row) -> node|string, num, sort }]
export function dataTable(columns, rows, { sort, dir, onSort, empty } = {}) {
  if (!rows.length) return h('div', { class: 'empty', text: empty || t('common.noResults') });
  const head = h('tr', {}, columns.map((c) => {
    const label = c.sort && onSort
      ? h('button', { type: 'button', class: 'sort-btn', onclick: () => onSort(c.sort) }, c.label,
        sort === c.sort ? (dir === 'desc' ? ' ▼' : ' ▲') : '')
      : c.label;
    return h('th', { class: c.num ? 'num' : '', scope: 'col', 'aria-sort': sort === c.sort ? (dir === 'desc' ? 'descending' : 'ascending') : undefined }, label);
  }));
  const body = rows.map((row) => h('tr', {}, columns.map((c) => {
    const value = c.render ? c.render(row) : row[c.key];
    return h('td', { class: c.num ? 'num' : '' }, value === null || value === undefined || value === '' ? t('common.none') : value);
  })));
  return h('div', { class: 'table-wrap' }, h('table', { class: 'data' }, h('thead', {}, head), h('tbody', {}, body)));
}

export function pager({ page, totalPages, totalItems, onPage }) {
  return h('nav', { class: 'pager', 'aria-label': 'pages' },
    h('span', { text: t('common.records', { n: formatCount(totalItems) }) }),
    totalPages > 1 ? h('span', { class: 'actions' },
      h('button', { type: 'button', class: 'btn btn-sm', disabled: page <= 0, onclick: () => onPage(page - 1), text: t('common.previous') }),
      h('span', { text: t('common.page', { page: page + 1, pages: totalPages }) }),
      h('button', { type: 'button', class: 'btn btn-sm', disabled: page + 1 >= totalPages, onclick: () => onPage(page + 1), text: t('common.next') }))
      : null);
}

const SVG = 'http://www.w3.org/2000/svg';
function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) el.setAttribute(k, String(v));
  return el;
}

// Completion ring: solid arc = current, light arc = forecast.
export function ring(current, forecast, label, onClick) {
  const r = 40; const c = 2 * Math.PI * r;
  const root = svg('svg', { viewBox: '0 0 100 100', role: 'img', 'aria-label': `${label}: ${formatPercent(current)} → ${formatPercent(forecast)}` });
  root.append(svg('circle', { cx: 50, cy: 50, r, fill: 'none', stroke: '#ece9e1', 'stroke-width': 10 }));
  root.append(svg('circle', { cx: 50, cy: 50, r, fill: 'none', stroke: '#8fd0b4', 'stroke-width': 10, 'stroke-dasharray': `${(forecast || 0) / 100 * c} ${c}`, transform: 'rotate(-90 50 50)' }));
  root.append(svg('circle', { cx: 50, cy: 50, r, fill: 'none', stroke: '#2f6fd6', 'stroke-width': 10, 'stroke-dasharray': `${(current || 0) / 100 * c} ${c}`, transform: 'rotate(-90 50 50)', 'stroke-linecap': 'butt' }));
  const text = svg('text', { x: 50, y: 52, 'text-anchor': 'middle', 'font-size': 17, 'font-weight': 700, fill: '#1c252d' });
  text.textContent = formatPercent(current);
  const sub = svg('text', { x: 50, y: 67, 'text-anchor': 'middle', 'font-size': 9, fill: '#5b646b' });
  sub.textContent = `→ ${formatPercent(forecast)}`;
  root.append(text, sub);
  const el = h(onClick ? 'button' : 'div', { type: onClick ? 'button' : undefined, class: 'ring' }, root, h('span', { text: label }));
  if (onClick) el.addEventListener('click', onClick);
  return el;
}

// Donut chart of segments [{label, value, color}].
export function donut(segments, centerText, centerSub) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r = 38; const c = 2 * Math.PI * r;
  const root = svg('svg', { viewBox: '0 0 100 100', width: 140, height: 140, role: 'img', 'aria-label': segments.map((s) => `${s.label}: ${s.value}`).join(', ') });
  let offset = 0;
  for (const seg of segments) {
    if (!seg.value) continue;
    const len = seg.value / total * c;
    root.append(svg('circle', { cx: 50, cy: 50, r, fill: 'none', stroke: seg.color, 'stroke-width': 14, 'stroke-dasharray': `${len} ${c - len}`, 'stroke-dashoffset': -offset, transform: 'rotate(-90 50 50)' }));
    offset += len;
  }
  const text = svg('text', { x: 50, y: 52, 'text-anchor': 'middle', 'font-size': 18, 'font-weight': 700, fill: '#1c252d' });
  text.textContent = centerText;
  root.append(text);
  if (centerSub) {
    const sub = svg('text', { x: 50, y: 65, 'text-anchor': 'middle', 'font-size': 8, fill: '#5b646b' });
    sub.textContent = centerSub;
    root.append(sub);
  }
  return root;
}

export function meter(current, forecast, tall = false) {
  return h('div', { class: `meter ${tall ? 'tall' : ''}`, role: 'img', 'aria-label': `${formatPercent(current)} → ${formatPercent(forecast)}` },
    forecast !== undefined && forecast !== null ? h('span', { class: 'forecast', style: `width:${Math.min(forecast, 100)}%` }) : null,
    h('span', { style: `width:${Math.min(current || 0, 100)}%` }));
}

// Horizontal stacked bars: rows [{label, parts:[{value,color,label}], total, onClick}]
export function barRows(rows, max) {
  const top = max || Math.max(1, ...rows.map((r) => r.parts.reduce((s, p) => s + p.value, 0)));
  return h('div', { class: 'bar-rows' }, rows.map((row) => {
    const sum = row.parts.reduce((s, p) => s + p.value, 0);
    const track = h('div', { class: 'bar-track' }, row.parts.filter((p) => p.value > 0).map((p) =>
      h('span', { style: `width:${p.value / top * 100}%;background:${p.color}`, title: `${p.label}: ${p.value}` })));
    const content = [h('span', { text: row.label }), track, h('span', { class: 'mono', text: row.total ?? formatCount(sum) })];
    if (!row.onClick) return h('div', { class: 'bar-row' }, content);
    return h('div', { class: 'bar-row' }, h('button', { type: 'button', onclick: row.onClick, 'aria-label': `${row.label}: ${sum}` }, content));
  }));
}

export function legend(items) {
  return h('div', { class: 'legend' }, items.map((i) => h('span', {}, h('i', { style: `background:${i.color}` }), i.label)));
}

export function tabs(items, selected, onSelect) {
  return h('div', { class: 'tabs', role: 'tablist' }, items.map((item) =>
    h('button', { type: 'button', role: 'tab', 'aria-selected': item.key === selected ? 'true' : 'false', onclick: () => onSelect(item.key), text: item.label })));
}

export function field(label, control, { error, hint, span } = {}) {
  const id = control.id || `f-${Math.random().toString(36).slice(2)}`;
  control.id = id;
  return h('div', { class: `field ${error ? 'invalid' : ''} ${span ? 'span-all' : ''}` },
    h('label', { for: id, text: label }), control,
    hint ? h('span', { class: 'muted small', text: hint }) : null,
    h('span', { class: 'error', text: error || '' }));
}

export function selectEl(options, value, { includeEmpty, emptyLabel, name: nameAttr, multiple } = {}) {
  const sel = h('select', { class: 'select', name: nameAttr, multiple });
  if (includeEmpty) sel.append(h('option', { value: '', text: emptyLabel || t('common.all') }));
  for (const o of options) {
    const opt = h('option', { value: o.value, text: o.label });
    if (multiple ? (value || []).includes(o.value) : String(value ?? '') === String(o.value)) opt.selected = true;
    sel.append(opt);
  }
  return sel;
}

export function listOptions(list, { withCode = false, activeOnly = true } = {}) {
  return list.filter((e) => !activeOnly || !e.archived).map((e) => ({ value: e.id, label: withCode && e.code ? `${e.code} · ${name(e)}` : name(e) }));
}

export function loadingBox() { return h('div', { class: 'loading', text: t('common.loading') }); }
export function errorBox(error, retry) {
  return h('div', { class: 'error-box', role: 'alert' }, error.message || t('errors.generic'), ' ',
    retry ? h('button', { type: 'button', class: 'btn btn-sm', onclick: retry, text: t('common.retry') }) : null);
}

export function toast(message, isError = false) {
  const el = h('div', { class: `toast ${isError ? 'error' : ''}`, role: isError ? 'alert' : 'status', text: message });
  document.getElementById('toasts').append(el);
  window.setTimeout(() => el.remove(), isError ? 7000 : 3500);
}

export function dl(items) {
  return h('dl', { class: 'dl' }, items.filter(Boolean).map(([label, value]) =>
    h('div', {}, h('dt', { text: label }), h('dd', {}, value === null || value === undefined || value === '' ? t('common.none') : value))));
}

export function card(title, content, { actions, foot, className = '' } = {}) {
  return h('section', { class: `card ${className}` },
    title || actions ? h('div', { class: 'card-head' }, title ? h('h2', { text: title }) : h('span'), actions || null) : null,
    content, foot ? h('div', { class: 'card-foot' }, foot) : null);
}

// Audit history (GET /history/...). fieldLabel(field) names a field in the interface language.
export function historyList(events, fieldLabel = (f) => f) {
  if (!events.length) return h('div', { class: 'empty', text: t('history.empty') });
  return h('ul', { class: 'timeline' }, events.map((e) => h('li', {},
    h('div', {}, h('strong', { text: t(`history.${e.action}`) || e.action }), ' · ', formatDateTime(e.occurredAt), ' · ',
      h('span', { class: 'muted', text: t('history.by', { name: e.actor.displayName }) })),
    e.reason ? h('div', { class: 'muted small', text: e.reason }) : null,
    e.action === 'UPDATE' && e.changes.length ? h('ul', { class: 'change-list' }, e.changes.slice(0, 12).map((c) =>
      h('li', { text: t('history.field', { field: fieldLabel(c.field), from: display(c.from), to: display(c.to) }) }))) : null)));
}
function display(value) {
  if (value === null || value === undefined || value === '') return t('common.none');
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value);
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDateTime(value);
  return String(value);
}

export function setBusy(container, node) { replace(container, node || loadingBox()); }

export function iconButton(iconName, label, onClick, cls = 'btn') {
  return h('button', { type: 'button', class: cls, onclick: onClick }, icon(iconName), label);
}

export function categoryGlyph(code) {
  return { UAV: 'drone', UGV: 'vehicle', USV: 'boat', UUV: 'sub' }[code] || 'drone';
}

// Chart colours of the status colour names (STATUS_DEF.color).
export const COLORS = { green: '#12804a', amber: '#e3a92b', red: '#d24b3e', blue: '#2f6fd6', purple: '#6b52b8', teal: '#0f9488',
  grey: '#9aa3aa', orange: '#e0782b', pink: '#c94f8c', dark: '#41505c' };
export const RAG_COLORS = { GREEN: '#12a150', AMBER: '#e3a92b', RED: '#d24b3e', GREY: '#9aa3aa' };
export function colorOf(name) { return COLORS[name] || COLORS.grey; }
