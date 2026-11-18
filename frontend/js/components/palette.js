// The colours button (top bar and sign-in page): a small panel of ready-made palettes for this device, over the
// colours saved for everyone; for administrators also a way to those colours (Settings > Appearance).
import { h, icon } from '../lib/dom.js';
import { t } from '../labels.js';
import { PRESETS, personalPalette, setPersonalPalette } from '../lib/theme.js';

const KEYS = ['sidebar', 'primary', 'accent', 'background'];
const swatches = (c) => h('span', { class: 'theme-swatches' }, KEYS.map((k) => h('span', { class: 'theme-swatch', style: `background:${c[k]}` })));

export function paletteButton({ buttonClass, forEveryone }) {
  const button = h('button', { type: 'button', class: buttonClass, 'aria-label': t('top.colours'), title: t('top.colours'),
    'aria-haspopup': 'true', 'aria-expanded': 'false' }, icon('palette'));
  const anchor = h('div', { class: 'palette-anchor' }, button);
  let pop = null;

  function outside(event) { if (pop && !anchor.contains(event.target)) close(false); }
  function onKey(event) { if (event.key === 'Escape') { event.preventDefault(); close(true); } }
  function close(focusButton) {
    if (!pop) return;
    pop.remove();
    pop = null;
    button.setAttribute('aria-expanded', 'false');
    document.removeEventListener('pointerdown', outside, true);
    document.removeEventListener('keydown', onKey, true);
    if (focusButton) button.focus();
  }
  function open() {
    const current = personalPalette();
    const option = (key, label, colours) => h('button', { type: 'button', class: 'palette-option',
      'aria-pressed': current === key ? 'true' : 'false', onclick: () => { setPersonalPalette(key); close(true); } },
    colours ? swatches(colours) : h('span', { class: 'palette-default-mark' }, icon('restore')), h('span', { text: label }));
    pop = h('div', { class: 'palette-pop', role: 'dialog', 'aria-label': t('top.colours') },
      h('div', { class: 'palette-title', text: t('top.colours') }),
      h('div', { class: 'palette-list' },
        option(null, t('top.paletteDefault'), null),
        Object.entries(PRESETS).map(([key, colours]) => option(key, t(`settings.appearance.presets.${key}`), colours))),
      h('div', { class: 'palette-note', text: t('top.paletteNote') }),
      forEveryone ? h('a', { class: 'palette-link', href: '/settings?tab=appearance', onclick: () => close(false) },
        icon('settings'), t('top.paletteForEveryone')) : null);
    anchor.append(pop);
    button.setAttribute('aria-expanded', 'true');
    document.addEventListener('pointerdown', outside, true);
    document.addEventListener('keydown', onKey, true);
    const first = pop.querySelector('.palette-option[aria-pressed="true"]') || pop.querySelector('.palette-option');
    if (first) first.focus();
  }

  button.addEventListener('click', () => (pop ? close(true) : open()));
  return anchor;
}
