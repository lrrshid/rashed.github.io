// Sign-in page (local passwords on the demo, the company directory with AUTH_MODE=ldap).
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { language, setLanguage } from '../lib/i18n.js';
import { t } from '../labels.js';
import { capabilityScene, followPointer } from '../components/scene.js';
import { mode, setMode } from '../lib/theme.js';
import { paletteButton } from '../components/palette.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
// Small line icons inside the fields (decorative): a person and a padlock.
const FIELD_ICONS = {
  user: ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M4 20c1.4-3.6 4.4-5.5 8-5.5s6.6 1.9 8 5.5'],
  lock: ['M6 11h12v9H6z', 'M8.5 11V8a3.5 3.5 0 0 1 7 0v3', 'M12 15v2'],
};
function fieldIcon(name) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'login-field-icon');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  for (const d of FIELD_ICONS[name]) {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}

export function renderLogin(container, options, onSignedIn) {
  const username = h('input', { class: 'input', id: 'login-user', name: 'username', autocomplete: 'username', required: true });
  const password = h('input', { class: 'input', id: 'login-pass', name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const error = h('div', { class: 'error-box', role: 'alert', hidden: true });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary login-submit', text: t('auth.submit') });
  const field = (id, label, input, iconName) => h('div', { class: 'field' }, h('label', { for: id, text: label }),
    h('div', { class: 'login-input' }, fieldIcon(iconName), input));
  const form = h('form', { novalidate: true },
    field('login-user', t('auth.username'), username, 'user'),
    field('login-pass', t('auth.password'), password, 'lock'),
    error, submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    try {
      const session = await api.post('/session', { username: username.value.trim(), password: password.value });
      onSignedIn(session);
    } catch (err) {
      error.textContent = err.code === 'LOGIN_FAILED' ? t('auth.failed') : err.message;
      error.hidden = false;
      password.value = '';
      password.focus();
    } finally {
      submit.disabled = false;
    }
  });
  const other = language() === 'ar' ? 'en' : 'ar';
  // The animated capability scene fills the page; the system's name on one side, the sign-in card on the other.
  const hero = h('div', { class: 'login-hero' },
    h('img', { class: 'login-hero-logo', src: '/assets/icons/ng-logo.png', alt: '' }),
    h('div', { class: 'login-kicker', text: t('app.subtitle') }),
    h('div', { class: 'login-title', text: t('app.name') }),
    h('div', {}, h('div', { class: 'login-rule' }), h('p', { class: 'login-pillars' },
      ['pillarDevelopment', 'pillarReadiness', 'pillarExcellence'].map((key, i) => [i ? h('i', { 'aria-hidden': 'true' }) : null,
        h('span', { text: t(`auth.${key}`) })]))),
    h('div', { class: 'login-chips' }, ['UAV', 'UGV', 'USV', 'UUV', 'AI'].map((code) => h('span', { class: 'login-chip', text: code }))));
  // Top corner (top right in Arabic), as in the top bar: light / dark mode and the colours for this browser (the
  // panel also leads to the colours for everyone, opened after a system administrator signs in).
  const modeBtn = h('button', { type: 'button', class: 'login-quick-btn', 'aria-label': t('top.darkMode'), title: t('top.darkMode'),
    'aria-pressed': mode() === 'dark' ? 'true' : 'false' }, icon(mode() === 'dark' ? 'sun' : 'moon'));
  modeBtn.addEventListener('click', () => {
    const next = mode() === 'dark' ? 'light' : 'dark';
    setMode(next);
    modeBtn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    replace(modeBtn, icon(next === 'dark' ? 'sun' : 'moon'));
  });
  const quick = h('div', { class: 'login-quick' }, modeBtn, paletteButton({ buttonClass: 'login-quick-btn', forEveryone: true }));
  // Arrived from the colours button: say why to sign in.
  const forColours = window.location.pathname === '/settings' && new URLSearchParams(window.location.search).get('tab') === 'appearance';
  const card = h('div', { class: 'login-card' },
    h('div', { class: 'login-card-head' },
      h('img', { class: 'login-card-emblem', src: '/assets/icons/ng-logo.png', alt: '' }),
      h('h1', { text: t('auth.title') }),
      h('p', { class: 'login-card-sub', text: forColours ? t('auth.signInForColours')
        : options.authMode === 'ldap' ? t('auth.directoryHint') : t('auth.cardHint') }),
      h('div', { class: 'login-ornament' }, h('span'), h('i'), h('span'))),
    form,
    h('div', { class: 'login-lang' }, h('button', { type: 'button', class: 'btn btn-ghost btn-sm', lang: other,
      text: other === 'ar' ? 'العربية' : 'English', onclick: () => setLanguage(other) })));
  const wrap = h('div', { class: 'login-wrap' }, capabilityScene('full'), quick, hero, card);
  replace(container, wrap);
  followPointer(wrap);
  username.focus();
}
