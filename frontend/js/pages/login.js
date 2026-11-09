// Sign-in page (local passwords on the demo, the company directory with AUTH_MODE=ldap).
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { language, setLanguage } from '../lib/i18n.js';
import { t } from '../labels.js';

export function renderLogin(container, options, onSignedIn) {
  const username = h('input', { class: 'input', id: 'login-user', name: 'username', autocomplete: 'username', required: true });
  const password = h('input', { class: 'input', id: 'login-pass', name: 'password', type: 'password', autocomplete: 'current-password', required: true });
  const error = h('div', { class: 'error-box', role: 'alert', hidden: true });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary', text: t('auth.submit') });
  const form = h('form', { novalidate: true },
    h('div', { class: 'field' }, h('label', { for: 'login-user', text: t('auth.username') }), username),
    h('div', { class: 'field' }, h('label', { for: 'login-pass', text: t('auth.password') }), password),
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
  // One-click demo sign-in. Only offered when the server says the public mock accounts exist (demo profile, local
  // machine, local passwords); it fills the form and submits it, so the server checks it like any other sign-in.
  const tryDemo = options.mockAccounts ? h('button', { type: 'button', class: 'btn login-demo', text: t('auth.tryDemo'),
    onclick: () => { username.value = 'mock.admin'; password.value = 'Mock-Pass-123'; form.requestSubmit(); } }) : null;
  const other = language() === 'ar' ? 'en' : 'ar';
  replace(container, h('div', { class: 'login-wrap' }, h('div', { class: 'login-card' },
    h('div', { class: 'brand' }, h('img', { class: 'brand-mark', src: '/assets/icons/ng-logo.png', alt: '' }),
      h('div', {}, h('div', { class: 'brand-name', text: t('app.name') }), h('div', { class: 'brand-sub', text: t('app.subtitle') }))),
    h('h1', { text: t('auth.title') }),
    options.authMode === 'ldap' ? h('p', { class: 'muted small', text: t('auth.directoryHint') }) : null,
    form,
    tryDemo,
    options.mockAccounts ? h('div', { class: 'mock-hint', text: t('auth.mockHint') }) : null,
    h('div', { class: 'login-lang' }, h('button', { type: 'button', class: 'btn btn-ghost btn-sm', lang: other,
      text: other === 'ar' ? 'العربية' : 'English', onclick: () => setLanguage(other) })))));
  username.focus();
}
