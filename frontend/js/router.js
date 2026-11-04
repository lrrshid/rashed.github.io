// History-API router. Each route lazily imports its page module, whose render(container, ctx) draws the page and may
// return a cleanup function. ctx: { params, query, navigate, setQuery }.
import { h, markInAppNavigation, replace } from './lib/dom.js';
import { t } from './labels.js';

const routes = [];
let cleanup = null;
let onNavigate = () => {};
let renderToken = 0;

export function route(pattern, loader, meta = {}) {
  const keys = [];
  const regex = new RegExp(`^${pattern.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; })}/?$`);
  routes.push({ regex, keys, loader, meta, pattern });
}

export function setNavigateHandler(fn) { onNavigate = fn; }

export function navigate(path, { replace: replaceState = false } = {}) {
  if (replaceState) window.history.replaceState({}, '', path);
  else window.history.pushState({}, '', path);
  markInAppNavigation();
  render();
}

export function currentQuery() {
  return Object.fromEntries(new URLSearchParams(window.location.search));
}

// Keep page filters in the address bar (shareable, survive a refresh) without re-rendering.
export function setQuery(values) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(values)) {
    if (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length)) continue;
    params.set(k, Array.isArray(v) ? v.join(',') : String(v));
  }
  const text = params.toString();
  window.history.replaceState({}, '', `${window.location.pathname}${text ? `?${text}` : ''}`);
}

export async function render() {
  const token = ++renderToken;
  const main = document.getElementById('main');
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  const path = window.location.pathname;
  const match = routes.map((r) => ({ r, m: r.regex.exec(path) })).find((x) => x.m);
  onNavigate(path, match ? match.r.meta : {});
  if (!match) {
    replace(main, h('div', { class: 'page' }, h('div', { class: 'empty', text: t('errors.notFound') })));
    return;
  }
  const params = {};
  match.r.keys.forEach((k, i) => { params[k] = decodeURIComponent(match.m[i + 1]); });
  replace(main, h('div', { class: 'loading', text: t('common.loading') }));
  const module = await match.r.loader();
  if (token !== renderToken) return;
  const container = h('div', { class: 'page' });
  replace(main, container);
  const result = await module.render(container, { params, query: currentQuery(), navigate, setQuery, meta: match.r.meta });
  if (token === renderToken && typeof result === 'function') cleanup = result;
  window.scrollTo(0, 0);
}

export function startRouter() {
  window.addEventListener('popstate', () => render());
  // In-app links: <a href="/..."> without target navigate without a page load.
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    if (!link || link.target || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const url = new URL(link.href, window.location.origin);
    if (url.origin !== window.location.origin || url.pathname.startsWith('/api/') || link.hasAttribute('download')) return;
    event.preventDefault();
    navigate(url.pathname + url.search);
  });
  render();
}
