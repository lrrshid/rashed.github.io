// Settings > Users: adding many people from an Excel file (owner request, 24 Nov 2026; services/user_import.py).
// 1. Download the template (in the interface language). 2. Fill one row per person. 3. Choose the file: the server
// checks every row (nothing is written) and this window shows each row's state. 4. Import: every row is added in one
// go, only when no row has a problem. Passwords never come back from the server.
import { ApiError, download, request } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { language } from '../lib/i18n.js';
import { name, t } from '../labels.js';
import { openModal } from '../components/modal.js';
import { badge, dataTable, toast } from '../components/ui.js';

const MAX_BYTES = 2 * 1024 * 1024;

export function downloadUserTemplate() {
  return download('/users/import-template', { lang: language() === 'ar' ? 'ar' : 'en' }).catch((e) => toast(e.message, true));
}

function send(path, file) {
  const form = new FormData();
  form.append('file', file, file.name);
  return request('POST', path, { form });
}

// One problem or warning in words: a code with its value or row number (settings.users.import.problems / warnings).
function says(kind, item) {
  return t(`settings.users.import.${kind}.${item.code}`, { value: item.value ?? '', row: item.row ?? '' });
}

export function openUserImport(onDone) {
  const file = h('input', { type: 'file', class: 'input', id: 'user-import-file', accept: '.xlsx,.csv' });
  const result = h('div', { class: 'import-result', 'aria-live': 'polite' });
  const go = h('button', { type: 'button', class: 'btn btn-primary', disabled: true, text: t('settings.users.import.go', { n: 0 }) });
  const close = h('button', { type: 'button', class: 'btn', text: t('common.cancel') });
  const modal = openModal({
    title: t('settings.users.import.title'), size: 'lg', footer: [close, go],
    body: h('div', {},
      h('ol', { class: 'import-steps' }, ['step1', 'step2', 'step3'].map((k) => h('li', { text: t(`settings.users.import.${k}`) }))),
      h('div', { class: 'conn-inline' },
        h('button', { type: 'button', class: 'btn', onclick: downloadUserTemplate }, icon('download'), t('settings.users.import.template')),
        h('div', { class: 'field' }, h('label', { for: 'user-import-file', text: t('settings.users.import.file') }), file)),
      result),
  });
  close.addEventListener('click', () => modal.close(true));
  let chosen = null;

  async function check() {
    chosen = file.files[0] || null;
    go.disabled = true;
    if (!chosen) { replace(result); return; }
    if (chosen.size > MAX_BYTES) { replace(result, h('div', { class: 'error-box', text: t('settings.users.import.tooBig') })); return; }
    replace(result, h('p', { class: 'muted', text: t('settings.users.import.checking') }));
    let answer;
    try {
      answer = await send('/users/import/check', chosen);
    } catch (e) {
      const detail = e instanceof ApiError && e.fieldErrors.length ? e.fieldErrors[0].message : e.message;
      replace(result, h('div', { class: 'error-box', text: detail }));
      return;
    }
    go.textContent = t('settings.users.import.go', { n: answer.ready });
    go.disabled = !answer.canImport;
    replace(result,
      h('p', {}, h('strong', { text: t('settings.users.import.summary', { total: answer.total, ready: answer.ready }) }), ' ',
        answer.withProblems ? badge('red', t('settings.users.import.withProblems', { n: answer.withProblems })) : badge('green', t('settings.users.import.allReady'))),
      answer.withProblems ? h('p', { class: 'muted small', text: t('settings.users.import.fixFirst') }) : null,
      dataTable([
        { key: 'row', label: t('settings.users.import.row'), num: true, render: (r) => String(r.row) },
        { key: 'u', label: t('settings.users.username'), render: (r) => h('span', { class: 'mono', dir: 'ltr', text: r.username || t('common.none') }) },
        { key: 'n', label: t('settings.users.displayName'), render: (r) => r.displayName },
        { key: 'r', label: t('settings.users.role'), render: (r) => (r.role ? name(r.role) : t('common.none')) },
        { key: 'g', label: t('settings.users.departments'), render: (r) => r.groups.map((g) => name(g)).join('، ') || t('common.none') },
        { key: 'p', label: t('settings.users.import.password'), render: (r) => (r.password ? t(`settings.users.import.passwordStates.${r.password}`) : t('common.none')) },
        { key: 's', label: t('settings.users.import.state'), render: (r) => h('div', { class: 'import-state' },
          r.problems.length ? r.problems.map((p) => badge('red', says('problems', p))) : badge('green', t('settings.users.import.ok')),
          r.warnings.map((w) => badge('amber', says('warnings', w)))) },
      ], answer.rows, { empty: t('settings.users.import.empty') }));
  }

  file.addEventListener('change', check);
  go.addEventListener('click', async () => {
    if (!chosen) return;
    go.disabled = true;
    try {
      const done = await send('/users/import', chosen);
      toast(t('settings.users.import.done', { n: done.added }));
      modal.close(true);
      if (onDone) onDone();
    } catch (e) {
      toast(e.message, true);
      check();  // show again what stops it
    }
  });
  return modal;
}
