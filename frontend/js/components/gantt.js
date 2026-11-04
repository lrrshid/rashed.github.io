// SVG Gantt / timeline. Time always runs left to right (as in the brochure, also in Arabic); labels sit in a
// fixed column on the reading-start side of the chart. rows: [{ label, sub, href, start, end, forecastEnd, progress,
// color, done, markers: [{ date, label, color, shape }], indent }] with dates as YYYY-MM-DD.
import { h } from '../lib/dom.js';
import { isRtl, locale } from '../lib/i18n.js';
import { t } from '../labels.js';
import { navigate } from '../router.js';

const NS = 'http://www.w3.org/2000/svg';
function el(tag, attrs = {}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}
const DAY = 86_400_000;
const toMs = (iso) => Date.parse(`${iso}T00:00:00Z`);

export function gantt(rows, { from, to, today, scale = 'MONTH', rowHeight = 28, labelWidth = 300, width = 1200 } = {}) {
  const start = toMs(from);
  const end = toMs(to);
  const chartW = Math.max(width - labelWidth, 400);
  const x = (iso) => labelWidth + ((toMs(iso) - start) / (end - start)) * chartW;
  const headerH = 34;
  const height = headerH + rows.length * rowHeight + 10;
  const svg = el('svg', { width: labelWidth + chartW, height, role: 'img', 'aria-label': t('gantt.title'), direction: 'ltr' });

  // Ticks: months, quarters or years.
  const ticks = [];
  const d = new Date(start);
  d.setUTCDate(1);
  if (scale !== 'MONTH') d.setUTCMonth(Math.floor(d.getUTCMonth() / 3) * 3);
  if (scale === 'YEAR') d.setUTCMonth(0);
  const step = scale === 'MONTH' ? 1 : scale === 'QUARTER' ? 3 : 12;
  while (d.getTime() <= end) {
    if (d.getTime() >= start) ticks.push(new Date(d));
    d.setUTCMonth(d.getUTCMonth() + step);
  }
  const fmtMonth = new Intl.DateTimeFormat(locale(), { month: 'short', year: '2-digit', timeZone: 'UTC' });
  for (const tick of ticks) {
    const tx = labelWidth + ((tick.getTime() - start) / (end - start)) * chartW;
    svg.append(el('line', { x1: tx, x2: tx, y1: headerH - 6, y2: height, stroke: '#ebe7de' }));
    const label = scale === 'MONTH' ? fmtMonth.format(tick)
      : scale === 'QUARTER' ? `Q${Math.floor(tick.getUTCMonth() / 3) + 1} ${tick.getUTCFullYear()}` : String(tick.getUTCFullYear());
    svg.append(el('text', { x: tx + 3, y: 18, class: 'muted-text' }, label));
  }
  svg.append(el('line', { x1: labelWidth, x2: labelWidth + chartW, y1: headerH - 6, y2: headerH - 6, stroke: '#d8d3c7' }));

  rows.forEach((row, i) => {
    const y = headerH + i * rowHeight;
    if (i % 2 === 1) svg.append(el('rect', { x: 0, y, width: labelWidth + chartW, height: rowHeight, fill: '#faf9f6' }));
    const label = el('text', { x: 8 + (row.indent ? 16 : 0), y: y + (row.sub ? 12 : 17), 'font-weight': row.indent ? 400 : 600, direction: isRtl() ? 'rtl' : 'ltr' },
      truncate(row.label, row.indent ? 44 : 40));
    if (isRtl()) { label.setAttribute('x', labelWidth - 8 - (row.indent ? 16 : 0)); label.setAttribute('text-anchor', 'start'); }
    svg.append(label);
    if (row.sub) {
      const sub = el('text', { x: isRtl() ? labelWidth - 8 : 8 + (row.indent ? 16 : 0), y: y + 24, class: 'muted-text', 'font-size': 10, direction: isRtl() ? 'rtl' : 'ltr' }, truncate(row.sub, 50));
      svg.append(sub);
    }
    if (row.href) {
      const hit = el('rect', { x: 0, y, width: labelWidth, height: rowHeight, fill: 'transparent', cursor: 'pointer', tabindex: 0, role: 'link', 'aria-label': row.label });
      hit.addEventListener('click', () => navigate(row.href));
      hit.addEventListener('keydown', (e) => { if (e.key === 'Enter') navigate(row.href); });
      svg.append(hit);
    }
    if (!row.start || !row.end) return;
    const bx = Math.max(x(row.start), labelWidth);
    const bx2 = Math.min(x(row.end), labelWidth + chartW);
    const barY = y + 7;
    const barH = rowHeight - 14;
    if (bx2 > bx) {
      svg.append(el('rect', { x: bx, y: barY, width: bx2 - bx, height: barH, rx: 3, fill: row.color ? `${row.color}40` : '#c6d8f5', stroke: row.late ? '#d24b3e' : 'none' }));
      if (row.progress) {
        svg.append(el('rect', { x: bx, y: barY, width: (bx2 - bx) * Math.min(row.progress, 100) / 100, height: barH, rx: 3, fill: row.color || '#2f6fd6' }));
      }
      const tip = el('title', {}, `${row.label}: ${row.start} → ${row.end}${row.forecastEnd ? ` (${t('gantt.slip')} ${row.forecastEnd})` : ''}`);
      svg.lastChild.append(tip);
    }
    if (row.forecastEnd && row.forecastEnd > row.end) {
      const fx = Math.min(x(row.forecastEnd), labelWidth + chartW);
      svg.append(el('line', { x1: bx2, x2: fx, y1: barY + barH / 2, y2: barY + barH / 2, stroke: '#d24b3e', 'stroke-width': 2, 'stroke-dasharray': '3 3' }));
      svg.append(el('path', { d: diamond(fx, barY + barH / 2, 5), fill: '#d24b3e' }));
    }
    for (const m of row.markers || []) {
      if (!m.date) continue;
      const mx = x(m.date);
      if (mx < labelWidth || mx > labelWidth + chartW) continue;
      const shape = el('path', { d: diamond(mx, barY + barH / 2, 5), fill: m.color || '#16a34a', stroke: '#fff', 'stroke-width': 1 });
      shape.append(el('title', {}, `${m.label} · ${m.date}`));
      svg.append(shape);
    }
  });
  if (today) {
    const tx = x(today);
    if (tx >= labelWidth && tx <= labelWidth + chartW) {
      svg.append(el('line', { x1: tx, x2: tx, y1: headerH - 10, y2: height, stroke: '#d24b3e', 'stroke-width': 1.5 }));
      svg.append(el('text', { x: tx + 3, y: headerH - 12, fill: '#d24b3e', 'font-size': 10 }, t('gantt.today')));
    }
  }
  return h('div', { class: 'gantt', dir: 'ltr' }, svg);
}

function diamond(cx, cy, r) { return `M${cx} ${cy - r}L${cx + r} ${cy}L${cx} ${cy + r}L${cx - r} ${cy}Z`; }
function truncate(text, n) { const s = String(text || ''); return s.length > n ? `${s.slice(0, n - 1)}…` : s; }

export function rangeAround(rows, today, padDays = 30) {
  const dates = [];
  for (const r of rows) {
    for (const v of [r.start, r.end, r.forecastEnd]) if (v) dates.push(toMs(v));
    for (const m of r.markers || []) if (m.date) dates.push(toMs(m.date));
  }
  if (today) dates.push(toMs(today));
  if (!dates.length) return null;
  const iso = (ms) => new Date(ms).toISOString().slice(0, 10);
  return { from: iso(Math.min(...dates) - padDays * DAY), to: iso(Math.max(...dates) + padDays * DAY) };
}
