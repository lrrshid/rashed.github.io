// Display formatting. Instants arrive as ISO-8601 UTC and are shown in the company time zone; calendar dates
// (YYYY-MM-DD) are never shifted. Dates are dd/mm/yyyy in both languages, with Western digits.
import { t } from '../labels.js';
import { isRtl, locale } from './i18n.js';

let zone = 'Asia/Dubai';
export function setTimeZone(name) { if (name) zone = name; }
export function companyZone() { return zone; }

const cache = new Map();
function formatter(key, options) {
  const id = `${key}|${zone}`;
  if (!cache.has(id)) cache.set(id, new Intl.DateTimeFormat(locale(), { timeZone: zone, ...options }));
  return cache.get(id);
}
function partsOf(key, options, date) {
  const parts = {};
  for (const part of formatter(key, options).formatToParts(date)) if (part.type !== 'literal') parts[part.type] = part.value;
  return parts;
}
const DATE_PARTS = { day: '2-digit', month: '2-digit', year: 'numeric' };
const dmy = (p) => `${p.day}/${p.month}/${String(p.year).padStart(4, '0')}`;

export function formatDateTime(iso) {
  if (!iso) return t('common.none');
  const p = partsOf('dt', { ...DATE_PARTS, hour: '2-digit', minute: '2-digit' }, new Date(iso));
  return `${dmy(p)} ${p.dayPeriod ? `${p.hour}:${p.minute} ${p.dayPeriod}` : `${p.hour}:${p.minute}`}`;
}

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;
// YYYY-MM-DD -> dd/mm/yyyy (no time zone involved).
export function formatDate(value) {
  if (!value) return t('common.none');
  const m = ISO_DATE.exec(value);
  if (!m) return formatDateTime(value);
  return `${m[3]}/${m[2]}/${m[1]}`;
}
export const formatPlainDate = formatDate;

// "Oct 2026" style month label for charts.
export function formatMonth(value) {
  const m = ISO_DATE.exec(value);
  if (!m) return value;
  return new Intl.DateTimeFormat(locale(), { month: 'short', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(Date.UTC(+m[1], +m[2] - 1, 1)));
}

// dd/mm/yyyy typed text -> YYYY-MM-DD, or null.
export function parseDateText(text) {
  const raw = String(text || '');
  const iso = /^\s*(\d{4})-(\d{2})-(\d{2})\s*$/.exec(raw);
  const m = iso ? [null, iso[3], iso[2], iso[1]] : /^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\s*$/.exec(raw);
  if (!m) return null;
  const [d, mo, y] = [+m[1], +m[2], +m[3]];
  const date = new Date(Date.UTC(y, mo - 1, d));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== mo - 1 || date.getUTCDate() !== d) return null;
  return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

const numberFormats = new Map();
function numberFormat(options = {}) {
  const id = JSON.stringify(options);
  if (!numberFormats.has(id)) numberFormats.set(id, new Intl.NumberFormat(locale(), options));
  return numberFormats.get(id);
}
export function formatCount(n) { return numberFormat().format(n ?? 0); }
export function formatNumber(n, digits = 1, minDigits = 0) {
  if (n === null || n === undefined) return t('common.none');
  return numberFormat({ maximumFractionDigits: digits, minimumFractionDigits: minDigits }).format(n);
}
export function formatPercent(value) {
  if (value === null || value === undefined) return t('common.none');
  return numberFormat({ style: 'percent', maximumFractionDigits: 0 }).format(value / 100);
}
// AED amounts: millions as "12.16 M AED", thousands as "850 K AED", small ones in full.
export function formatMoney(value) {
  if (value === null || value === undefined) return t('common.none');
  if (Math.abs(value) >= 1_000_000) return t('common.million', { n: formatNumber(value / 1_000_000, 2) });
  if (Math.abs(value) >= 10_000) return t('common.thousand', { n: formatNumber(value / 1000, 0) });
  return `${formatNumber(value, 0)} ${t('common.aed')}`;
}
export function formatSigned(n) {
  const text = `${n > 0 ? '+' : n < 0 ? '−' : ''}${formatNumber(Math.abs(n), 1)}`;
  return isRtl() ? `⁦${text}⁩` : text;
}

let collator = null;
export function compareText(a, b) {
  if (!collator) collator = new Intl.Collator(locale(), { numeric: true, sensitivity: 'base' });
  return collator.compare(a ?? '', b ?? '');
}
export function searchFold(text) {
  return String(text ?? '').toLowerCase().replace(/[ً-ٰـ]/g, '').replace(/[أإآٱ]/g, 'ا')
    .replace(/ة/g, 'ه').replace(/ى/g, 'ي');
}
export function todayInZone() {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' })
    .formatToParts(new Date());
  const get = (type) => parts.find((p) => p.type === type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function daysBetween(fromIso, toIso) {
  const a = Date.parse(`${fromIso}T00:00:00Z`);
  const b = Date.parse(`${toIso}T00:00:00Z`);
  return Math.round((b - a) / 86_400_000);
}
