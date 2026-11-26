// User tracking «تتبع المستخدمين» (/user-tracking; owner request 25 Nov 2026). For the commander and the roles given
// tracking.view, never in a role preview (the server refuses everyone else). Every action of every person, carried
// out or refused: who, what, on which record, the outcome and why it failed, the date and time and the device
// (backend services/tracking_service.py). Two views: the actions, newest first, and the people with their totals.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canTrack, lookupList } from '../lib/state.js';
import { name, serverText, t } from '../labels.js';
import { formatCount, formatDateTime, formatDateTimeSeconds } from '../lib/format.js';
import { dateField } from '../components/date-field.js';
import { openModal } from '../components/modal.js';
import { badge, card, dataTable, dl, errorBox, kpiTile, loadingBox, pager, selectEl, tabs } from '../components/ui.js';
import { fieldLabel } from './field-labels.js';

const KINDS = ['SESSION', 'ADD', 'CHANGE', 'ARCHIVE', 'FILES', 'VIEW'];
const ACTION_COLORS = {
  SIGN_IN: 'grey', SIGN_OUT: 'grey', CONFIRM_PASSWORD: 'grey', CREATE: 'green', IMPORT: 'green', UPDATE: 'blue',
  ARCHIVE: 'orange', RESTORE: 'teal', DELETE: 'red', UPLOAD: 'purple', DOWNLOAD: 'purple', EXPORT: 'purple',
  CHECK_FILE: 'purple', VIEW: 'dark', VIEW_REPORT: 'dark', RUN_REPORT: 'dark',
};

// A code in words (tracking.actions / tracking.types), the code itself when it has none.
const label = (group, code) => { const s = t(`tracking.${group}.${code}`); return s.startsWith('tracking.') ? code : s; };
const roleName = (code) => { const r = lookupList('roles').find((x) => x.code === code); return r ? name(r) : (code || t('common.none')); };
const reasonOf = (a) => serverText(a.errorCode, a.errorMessage) || a.errorCode;

function recordCell(a) {
  if (!a.entityType && !a.record.code) return null;
  const parts = h('span', {},
    a.entityType ? h('span', { class: 'muted small', text: `${label('types', a.entityType)} ` }) : null,
    a.record.code ? h('span', { class: 'mono small', dir: 'ltr', text: a.record.code }) : null,
    a.record.nameEn ? h('span', { text: ` · ${name(a.record)}` }) : null);
  return a.link ? h('a', { href: a.link }, parts) : parts;
}

function resultCell(a) {
  return a.outcome === 'DONE' ? badge('green', t('tracking.results.DONE'))
    : h('div', { class: 'tracking-result' }, badge('red', t('tracking.results.FAILED')), h('div', { class: 'small', text: reasonOf(a) }));
}

async function openDetails(id) {
  let d;
  try { d = await api.get(`/tracking/actions/${id}`); } catch (e) { openModal({ title: t('tracking.detailsTitle'), body: errorBox(e) }); return; }
  openModal({
    title: t('tracking.detailsTitle'), size: 'lg',
    body: h('div', {},
      dl([
        [t('tracking.fields.when'), formatDateTimeSeconds(d.occurredAt)],
        [t('tracking.fields.user'), `${d.user.displayName || ''} (${d.user.username})`],
        [t('tracking.fields.role'), roleName(d.user.role)],
        [t('tracking.fields.action'), badge(ACTION_COLORS[d.action] || 'grey', label('actions', d.action))],
        [t('tracking.fields.record'), recordCell(d)],
        [t('tracking.fields.result'), resultCell(d)],
        d.errorFields.length ? [t('tracking.fields.fields'), d.errorFields.map((f) => fieldLabel(f)).join('، ')] : null,
        d.detail ? [t('tracking.fields.detail'), d.detail] : null,
        d.reason ? [t('tracking.fields.reason'), d.reason] : null,
        d.previewRole ? [t('tracking.fields.preview'), roleName(d.previewRole)] : null,
        [t('tracking.fields.device'), h('span', { class: 'mono', dir: 'ltr', text: d.ip || '' })],
        [t('tracking.fields.request'), h('span', { class: 'mono small', dir: 'ltr', text: `${d.method} ${d.path} · ${d.requestId || ''}` })],
      ]),
      d.changes.length ? h('div', {}, h('div', { class: 'section-label', text: t('tracking.fields.changes') }),
        h('ul', { class: 'change-list' }, d.changes.map((c) => h('li', { text: `${fieldLabel(c.field)}: ${c.from ?? '—'} → ${c.to ?? '—'}` }))))
        : null),
  });
}

export async function render(container, ctx) {
  if (!canTrack()) {
    container.append(h('div', { class: 'page-head' }, h('h1', { tabindex: '-1', text: t('tracking.title') })),
      h('p', { class: 'muted', text: t('tracking.notAllowed') }));
    return;
  }
  const f = { from: ctx.query.from || '', to: ctx.query.to || '', user: ctx.query.user || '', kind: ctx.query.kind || '',
    result: ctx.query.result || '', q: ctx.query.q || '' };
  let view = ctx.query.view === 'users' ? 'users' : 'log';
  let page = 0;
  let people = [];

  const from = dateField({ id: 'tr-from', value: f.from, label: t('tracking.fields.from') });
  const to = dateField({ id: 'tr-to', value: f.to, label: t('tracking.fields.to') });
  const userSel = h('select', { class: 'select', id: 'tr-user' });
  const kindSel = selectEl(KINDS.map((k) => ({ value: k, label: t(`tracking.kinds.${k}`) })), f.kind,
    { includeEmpty: true, emptyLabel: t('tracking.allKinds') });
  kindSel.id = 'tr-kind';
  const resultSel = selectEl(['DONE', 'FAILED'].map((r) => ({ value: r, label: t(`tracking.results.${r}`) })), f.result,
    { includeEmpty: true, emptyLabel: t('tracking.allResults') });
  resultSel.id = 'tr-result';
  const search = h('input', { class: 'input', id: 'tr-q', type: 'search', value: f.q, maxlength: 100, placeholder: t('tracking.searchHint') });
  const apply = h('button', { type: 'button', class: 'btn btn-primary' }, t('tracking.apply'));
  const field = (id, text, control) => h('div', { class: 'field' }, h('label', { for: id, text }), control);
  const kpis = h('div', { class: 'kpis' });
  const tabsBox = h('div');
  const body = h('div');

  const save = () => ctx.setQuery({ from: f.from || undefined, to: f.to || undefined, user: f.user || undefined,
    kind: f.kind || undefined, result: f.result || undefined, q: f.q || undefined, view: view === 'users' ? 'users' : undefined });
  const read = () => {
    f.from = from.input.value || ''; f.to = to.input.value || ''; f.user = userSel.value; f.kind = kindSel.value;
    f.result = resultSel.value; f.q = search.value.trim();
  };
  apply.addEventListener('click', () => { read(); page = 0; save(); load(); });
  search.addEventListener('keydown', (e) => { if (e.key === 'Enter') apply.click(); });

  container.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', { tabindex: '-1', text: t('tracking.title') }), h('div', { class: 'page-sub', text: t('tracking.subtitle') }))),
    card(null, h('div', { class: 'tracking-filters' },
      field('tr-from', t('tracking.fields.from'), from.node), field('tr-to', t('tracking.fields.to'), to.node),
      field('tr-user', t('tracking.fields.user'), userSel), field('tr-kind', t('tracking.fields.action'), kindSel),
      field('tr-result', t('tracking.fields.result'), resultSel), field('tr-q', t('tracking.search'), search),
      h('div', { class: 'field' }, h('span', { class: 'label', text: ' ' }), apply))),
    kpis, tabsBox, body);

  function drawTabs() {
    replace(tabsBox, tabs([{ key: 'log', label: t('tracking.tabs.log') }, { key: 'users', label: t('tracking.tabs.users') }], view,
      (key) => { view = key; save(); drawTabs(); show(); }));
  }

  async function loadPeople() {
    const d = await api.get('/tracking/users', { from: f.from || undefined, to: f.to || undefined });
    people = d.items;
    f.from = d.from; f.to = d.to;
    from.input.value = d.from; to.input.value = d.to;
    replace(userSel, h('option', { value: '', text: t('tracking.allUsers') }),
      people.map((u) => h('option', { value: u.id, text: `${u.displayName} (${u.username})`, selected: u.id === f.user || undefined })));
  }

  async function load() {
    replace(body, loadingBox());
    try { await loadPeople(); } catch (e) { replace(body, errorBox(e, load)); return; }
    show();
  }

  function show() {
    if (view === 'users') showPeople(); else showLog();
  }

  function showPeople() {
    replace(body, card(t('tracking.peopleTitle', { from: f.from.split('-').reverse().join('/'), to: f.to.split('-').reverse().join('/') }),
      dataTable([
        { key: 'name', label: t('tracking.fields.user'), render: (u) => h('span', {},
          h('span', { class: `presence ${u.online ? 'on' : ''}`, title: u.online ? t('tracking.online') : '' }), u.displayName) },
        { key: 'username', label: t('tracking.fields.username'), render: (u) => h('span', { class: 'mono small', dir: 'ltr', text: u.username }) },
        { key: 'role', label: t('tracking.fields.role'), render: (u) => name(u.role) },
        { key: 'state', label: t('tracking.fields.state'), render: (u) => (u.active ? (u.online ? badge('green', t('tracking.online')) : badge('grey', t('tracking.offline')))
          : badge('red', t('tracking.inactive'))) },
        { key: 'signIns', label: t('tracking.fields.signIns'), num: true, render: (u) => formatCount(u.signIns) },
        { key: 'failedSignIns', label: t('tracking.fields.failedSignIns'), num: true, render: (u) => (u.failedSignIns ? badge('red', formatCount(u.failedSignIns)) : '0') },
        { key: 'actions', label: t('tracking.fields.actions'), num: true, render: (u) => formatCount(u.actions) },
        { key: 'failed', label: t('tracking.fields.failed'), num: true, render: (u) => (u.failed ? badge('red', formatCount(u.failed)) : '0') },
        { key: 'last', label: t('tracking.fields.lastActivity'), render: (u) => (u.lastActivity ? formatDateTime(u.lastActivity) : t('common.none')) },
        { key: 'go', label: '', render: (u) => h('button', { type: 'button', class: 'btn btn-sm', onclick: () => {
          f.user = u.id; userSel.value = u.id; view = 'log'; page = 0; save(); drawTabs(); show();
        } }, t('tracking.showActions')) },
      ], people)));
  }

  async function showLog() {
    replace(body, loadingBox());
    let d;
    try {
      d = await api.get('/tracking/actions', { from: f.from || undefined, to: f.to || undefined, user: f.user || undefined,
        kind: f.kind || undefined, result: f.result || undefined, q: f.q || undefined, page, size: 50 });
    } catch (e) { replace(body, errorBox(e, showLog)); return; }
    const s = d.summary;
    replace(kpis,
      kpiTile({ label: t('tracking.kpi.total'), value: formatCount(s.total) }),
      kpiTile({ label: t('tracking.kpi.done'), value: formatCount(s.done), tone: 'green' }),
      kpiTile({ label: t('tracking.kpi.failed'), value: formatCount(s.failed), tone: s.failed ? 'red' : undefined }),
      kpiTile({ label: t('tracking.kpi.failedSignIns'), value: formatCount(s.failedSignIns), tone: s.failedSignIns ? 'red' : undefined }),
      kpiTile({ label: t('tracking.kpi.people'), value: formatCount(s.people) }),
      kpiTile({ label: t('tracking.kpi.online'), value: formatCount(people.filter((u) => u.online).length) }));
    replace(body, card(null, h('div', {},
      dataTable([
        { key: 'when', label: t('tracking.fields.when'), render: (a) => h('span', { class: 'nowrap', text: formatDateTimeSeconds(a.occurredAt) }) },
        { key: 'user', label: t('tracking.fields.user'), render: (a) => h('div', {}, h('strong', { text: a.user.displayName || a.user.username }),
          h('div', { class: 'mono muted small', dir: 'ltr', text: a.user.username })) },
        { key: 'role', label: t('tracking.fields.role'), render: (a) => roleName(a.user.role) },
        { key: 'action', label: t('tracking.fields.action'), render: (a) => badge(ACTION_COLORS[a.action] || 'grey', label('actions', a.action)) },
        { key: 'record', label: t('tracking.fields.record'), render: (a) => recordCell(a) },
        { key: 'result', label: t('tracking.fields.result'), render: (a) => resultCell(a) },
        { key: 'device', label: t('tracking.fields.device'), render: (a) => h('span', { class: 'mono small', dir: 'ltr', text: a.ip || '' }) },
        { key: 'more', label: '', render: (a) => h('button', { type: 'button', class: 'btn btn-sm', 'aria-label': t('tracking.fields.details'),
          title: t('tracking.fields.details'), onclick: () => openDetails(a.id) }, icon('history')) },
      ], d.items, { empty: t('tracking.none') }),
      d.totalPages > 1 ? pager({ page: d.page, totalPages: d.totalPages, totalItems: d.totalItems, onPage: (p) => { page = p; showLog(); } }) : null)));
  }

  drawTabs();
  await load();
}
