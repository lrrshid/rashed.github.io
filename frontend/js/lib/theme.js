// Interface colours (Settings > Appearance). Four colours are stored (side bar, buttons, accent, page background);
// the shades the style sheet uses are derived here and set as CSS variables on <html> through the CSSOM (no inline
// style attributes, see the content security policy). Light or dark mode is each viewer's choice, kept in this
// browser (top bar); in dark mode the surfaces are derived from the side-bar colour and the buttons take the accent.

export const DEFAULT_THEME = { sidebar: '#142029', primary: '#142029', accent: '#b9995a', background: '#f3f1ec' };

// Ready-made palettes offered in Settings > Appearance (labels: settings.appearance.presets.<key>).
export const PRESETS = {
  guard: DEFAULT_THEME,
  royal: { sidebar: '#0c0c0e', primary: '#1b1b1f', accent: '#c9a227', background: '#f4f1e8' },
  olive: { sidebar: '#1f2b1d', primary: '#2c3d29', accent: '#b5a46a', background: '#f1f0ea' },
  desert: { sidebar: '#3b2f22', primary: '#5a4632', accent: '#c8a165', background: '#f6f1e7' },
  naval: { sidebar: '#0d1b2e', primary: '#13325b', accent: '#c0a062', background: '#eef2f6' },
  slate: { sidebar: '#22272e', primary: '#384150', accent: '#8fb3c9', background: '#f2f3f5' },
};

const HEX = /^#[0-9a-f]{6}$/i;

function rgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function toHex(parts) {
  return `#${parts.map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`;
}

// a mixed toward b by the fraction t (0 = a, 1 = b).
export function mix(a, b, t) {
  const x = rgb(a); const y = rgb(b);
  return toHex(x.map((v, i) => v + (y[i] - v) * t));
}

function luminance(hex) {
  const [r, g, b] = rgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// Text on a coloured surface: light on dark colours, dark on light ones.
function onColour(hex) { return luminance(hex) > 0.45 ? '#1c252d' : '#ffffff'; }

export function normalise(theme) {
  const out = { ...DEFAULT_THEME };
  for (const key of Object.keys(out)) if (theme && HEX.test(theme[key] || '')) out[key] = theme[key].toLowerCase();
  return out;
}

const MODE_KEY = 'cpc.mode';
export function mode() { return document.documentElement.getAttribute('data-mode') === 'dark' ? 'dark' : 'light'; }

// Every variable applyTheme may set, so switching mode clears what the other mode set.
const THEMED = ['--navy-900', '--navy-800', '--navy-700', '--navy-600', '--on-navy', '--on-navy-muted', '--primary',
  '--primary-hover', '--on-primary', '--gold', '--gold-600', '--gold-100', '--bg', '--surface', '--surface-muted',
  '--border', '--border-strong'];

// The theme saved in Settings, to return to after an unsaved preview.
let saved = DEFAULT_THEME;
export function rememberTheme(theme) { saved = normalise(theme); }
export function savedTheme() { return saved; }

// This device's own palette (the colours button: a key of PRESETS), over the colours saved for everyone; null =
// those colours. Kept in this browser, like the language and the mode.
const PALETTE_KEY = 'cpc.palette';
let personalKey = null;
try {
  const stored = window.localStorage.getItem(PALETTE_KEY);
  if (stored && PRESETS[stored]) personalKey = stored;
} catch { /* storage unavailable: the colours saved for everyone */ }
export function personalPalette() { return personalKey; }
export function effectiveTheme() { return personalKey ? PRESETS[personalKey] : saved; }
export function setPersonalPalette(key) {
  personalKey = key && PRESETS[key] ? key : null;
  try {
    if (personalKey) window.localStorage.setItem(PALETTE_KEY, personalKey);
    else window.localStorage.removeItem(PALETTE_KEY);
  } catch { /* kept for this page only */ }
  applyTheme(effectiveTheme());
}

export function applyTheme(theme) {
  const c = normalise(theme);
  const lightSidebar = luminance(c.sidebar) > 0.45;
  const vars = {
    '--navy-900': mix(c.sidebar, '#000000', 0.28),
    '--navy-800': c.sidebar,
    '--navy-700': mix(c.sidebar, lightSidebar ? '#000000' : '#ffffff', 0.08),
    '--navy-600': mix(c.sidebar, lightSidebar ? '#000000' : '#ffffff', 0.16),
    '--on-navy': lightSidebar ? '#1c252d' : '#e9e6dd',
    '--on-navy-muted': lightSidebar ? '#4d5862' : mix(c.sidebar, '#ffffff', 0.58),
    '--gold': c.accent,
    '--gold-600': mix(c.accent, '#000000', 0.35),
  };
  if (mode() === 'dark') {
    // Dark surfaces tinted by the side-bar colour (a dark grey if that colour is light); gold buttons.
    const base = lightSidebar ? '#141a20' : c.sidebar;
    Object.assign(vars, {
      '--bg': mix(base, '#000000', 0.4), '--surface': mix(base, '#ffffff', 0.04), '--surface-muted': mix(base, '#ffffff', 0.09),
      '--border': mix(base, '#ffffff', 0.14), '--border-strong': mix(base, '#ffffff', 0.3),
      '--gold-100': mix(c.accent, base, 0.72),
      '--primary': c.accent, '--primary-hover': mix(c.accent, '#ffffff', 0.14), '--on-primary': onColour(c.accent),
    });
  } else {
    Object.assign(vars, {
      '--bg': c.background, '--surface-muted': mix(c.background, '#ffffff', 0.7), '--gold-100': mix(c.accent, '#ffffff', 0.82),
      '--primary': c.primary, '--primary-hover': mix(c.primary, luminance(c.primary) > 0.45 ? '#000000' : '#ffffff', 0.14),
      '--on-primary': onColour(c.primary),
    });
  }
  const style = document.documentElement.style;
  for (const name of THEMED) style.removeProperty(name);
  for (const [name, value] of Object.entries(vars)) style.setProperty(name, value);
  return c;
}

// Light or dark mode for this browser (top bar button); the saved colours are applied again for the new mode.
export function setMode(next) {
  const dark = next === 'dark';
  if (dark) document.documentElement.setAttribute('data-mode', 'dark');
  else document.documentElement.removeAttribute('data-mode');
  try { window.localStorage.setItem(MODE_KEY, dark ? 'dark' : 'light'); } catch { /* kept for this page only */ }
  applyTheme(effectiveTheme());
}
