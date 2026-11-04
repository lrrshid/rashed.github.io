// Tiny DOM builder. Text is always set with textContent — data is never parsed as HTML.

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key === 'dataset') Object.assign(el.dataset, value);
    // CSSOM, not the style attribute: the content security policy (style-src 'self') blocks style="" attributes.
    else if (key === 'style') el.style.cssText = value;
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
  append(el, children);
  return el;
}

export function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function replace(el, ...children) {
  clear(el);
  return append(el, children);
}

let idCounter = 0;
export function uid(prefix = 'id') {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
}

const SVG_NS = 'http://www.w3.org/2000/svg';

// Sprite icons that point along the reading direction: marked .icon-flip, which css/rtl.css mirrors in Arabic.
const DIRECTIONAL_ICONS = new Set(['move', 'chevron']);

// Icons from the local sprite (assets/icons/sprite.svg); always decorative — pair with visible text.
export function icon(name, className = 'icon') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', DIRECTIONAL_ICONS.has(name) ? `${className} icon-flip` : className);
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `/assets/icons/sprite.svg#${name}`);
  svg.append(use);
  return svg;
}

export function debounce(fn, wait = 250) {
  let timer = null;
  const debounced = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced;
}

// Run fn unless a call with the same key is still running (then resolve to null). For buttons that fetch something
// and then open a dialog: a double-click must not open two stacked dialogs editing the same record.
const busyKeys = new Set();
export async function exclusive(key, fn) {
  if (busyKeys.has(key)) return null;
  busyKeys.add(key);
  try {
    return await fn();
  } finally {
    busyKeys.delete(key);
  }
}

// Keeping keyboard focus across a re-render. Lists, pagers, sort headers and refreshed panels are rebuilt from
// scratch, which removes the focused control and drops focus to <body>. A control is recognised again in the new
// content by its data-focus-key, map station id, href, accessible name or text (plus its position among controls
// with the same key).
const FOCUS_CONTROLS = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';
function focusKeyOf(el) {
  if (el.dataset.focusKey) return `key:${el.dataset.focusKey}`;
  if (el.dataset.stationId) return `station:${el.dataset.stationId}`;
  return el.getAttribute('href') || el.getAttribute('aria-label') || (el.textContent || '').trim() || el.name || null;
}
function sameKey(container, key) {
  return [...container.querySelectorAll(FOCUS_CONTROLS)].filter((el) => focusKeyOf(el) === key);
}

// What has focus inside `container` (or null), to hand to restoreFocus after the re-render.
export function rememberFocus(container = document.body, el = document.activeElement) {
  if (!el || el === document.body || !container.contains(el) || !el.matches(FOCUS_CONTROLS)) return null;
  const key = focusKeyOf(el);
  if (!key) return null;
  const same = sameKey(container, key);
  return { key, index: same.indexOf(el), count: same.length };
}

// Focus the matching control in the new content, unless focus already went somewhere on purpose (a dialog, a
// heading). A match that is now disabled (e.g. "Next" on the last page) hands focus to an enabled control in the
// same pager or toolbar.
export function restoreFocus(container, saved) {
  if (!saved) return;
  const active = document.activeElement;
  if (active && active !== document.body && active.isConnected) return;
  const same = sameKey(container, saved.key);
  // Several controls share the key (e.g. repeated "Place" buttons): trust the position only if the list kept its
  // length; otherwise only a single remaining match is certainly the same control.
  let match = same.length === saved.count ? same[saved.index] : (same.length === 1 ? same[0] : null);
  if (match && match.disabled) {
    const group = match.closest('nav, [role="toolbar"], .pager, .segmented');
    match = group ? [...group.querySelectorAll('button, a[href]')].find((el) => !el.disabled) : null;
  }
  if (match) match.focus({ preventScroll: true });
}

export function keepFocus(container, render) {
  const saved = rememberFocus(container);
  const result = render();
  restoreFocus(container, saved);
  return result;
}

// Move focus to a page's heading after an in-app navigation (so screen-reader and keyboard users start at
// the new content). On the first render after a full page load focus is left alone, so the first Tab
// still reaches the skip link and header.
let inAppNavigation = false;
export function markInAppNavigation() {
  inAppNavigation = true;
}
export function focusHeading(el) {
  if (el && inAppNavigation) el.focus();
}

export function announce(message) {
  const region = document.getElementById('live-region');
  if (!region) return;
  region.textContent = '';
  window.setTimeout(() => { region.textContent = message; }, 50);
}
