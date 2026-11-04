// Small SVG builder (same idea as dom.js h()) for inline illustrations; attributes only, never HTML strings.

const NS = 'http://www.w3.org/2000/svg';

export function s(tag, attrs = {}, ...children) {
  const el = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    el.setAttribute(key, String(value));
  }
  for (const child of children.flat(Infinity)) if (child) el.append(child);
  return el;
}

// An animated-ready tick in a circle (stroke paths carry classes so motion.js can draw them).
export function checkMark(className = 'check-mark') {
  return s('svg', { class: className, viewBox: '0 0 52 52', 'aria-hidden': 'true', focusable: 'false' },
    s('circle', { class: 'check-ring', cx: 26, cy: 26, r: 23, fill: 'none', 'stroke-width': 3 }),
    s('path', { class: 'check-tick', d: 'M15 27.5l7.5 7.5L37.5 18.5', fill: 'none', 'stroke-width': 4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
}

// Static glyphs used by the submitter page (the shared sprite stays for the rest of the app).
const GLYPHS = {
  download: 'M12 3v11m0 0l-4-4m4 4l4-4M5 19h14',
  warning: 'M12 4l9 16H3L12 4zm0 6v4m0 3v.01',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  bolt: 'M13 3L5 14h6l-1 7 8-11h-6l1-7z',
  list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  clock: 'M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10 3a3 3 0 100-6 3 3 0 000 6z',
  play: 'M8 5l11 7-11 7V5z',
  calendar: 'M4 7h16M7 3v4m10-4v4M5 7h14v13H5V7z',
  grip: 'M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01',
  clip: 'M21 11.5l-8.5 8.5a5 5 0 01-7-7L14 4.5a3.5 3.5 0 015 5l-8.5 8.5a2 2 0 01-3-3L15 7.5',
  file: 'M14 3H6v18h12V7l-4-4zm0 0v4h4M9 13h6M9 17h6',
  image: 'M4 5h16v14H4V5zm0 11l5-5 4 4 2-2 5 5M15 9.5h.01',
  external: 'M14 4h6v6m0-6l-9 9M18 14v6H4V6h6',
  send: 'M21 3L10 14M21 3l-6.5 18-4.5-7-7-4.5L21 3z',
  undo: 'M9 14L4 9l5-5M4 9h10.5a5.5 5.5 0 010 11H11',
  hourglass: 'M6 3h12M6 21h12M7 3c0 5 5 6 5 9s-5 4-5 9M17 3c0 5-5 6-5 9s5 4 5 9',
  // Toward the reading start / end (the calendar's previous / next month).
  chevronStart: 'M15 6l-6 6 6 6',
  chevronEnd: 'M9 6l6 6-6 6',
};

// Glyphs that point along the reading direction (send, undo, open in a new tab, the calendar's month arrows):
// mirrored in Arabic (css/rtl.css).
const DIRECTIONAL_GLYPHS = new Set(['send', 'undo', 'external', 'chevronStart', 'chevronEnd']);

export function glyph(name, className = 'icon') {
  return s('svg', { class: DIRECTIONAL_GLYPHS.has(name) ? `${className} icon-flip` : className, viewBox: '0 0 24 24', 'aria-hidden': 'true', focusable: 'false', fill: 'none',
    stroke: 'currentColor', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' },
  s('path', { d: GLYPHS[name] }));
}
