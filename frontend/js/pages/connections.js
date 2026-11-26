// Settings > connections (system administrators): the sign-in method and the company directory, the main database,
// trusted certificates and approved destinations, and their history (ported from the Asset Availability project's
// Settings tab; API /api/v1/connections). A connection is edited as a draft: Save draft -> Test -> Apply (the database:
// Stage for restart). The server decides everything (what is valid, when a draft is tested enough, the lockout guard);
// this page shows its answers. Secrets are never shown or sent back: a saved one is "Saved", with Replace and Clear.
// A sensitive step answered 403 REAUTH_REQUIRED asks for the password, then tries once more.
import { ApiError, api, request } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { t } from '../labels.js';
import { formatDateTime } from '../lib/format.js';
import { confirmDialog, openModal } from '../components/modal.js';
import { badge, card, dataTable, pager, toast } from '../components/ui.js';
import { formDialog } from './forms.js';

export const CONNECTION_TABS = ['signIn', 'database', 'network', 'connLog'];

const STATE_COLOR = { ACTIVE: 'green', IN_USE: 'green', STAGED: 'amber', DRAFT: 'amber', DISABLED: 'grey', NOT_CONFIGURED: 'grey' };
const HEALTH_COLOR = { HEALTHY: 'green', DEGRADED: 'amber', FAILED: 'red', UNTESTED: 'grey', STALE: 'grey', NOT_CONFIGURED: 'grey' };
const OUTCOME_COLOR = { PASSED: 'green', WARNING: 'amber', FAILED: 'red', SKIPPED: 'grey' };
const CERT_COLOR = { VALID: 'green', EXPIRING: 'amber', EXPIRED: 'red' };
// The label group of each kind of connection's fields (fields, hints, examples, choices, secrets).
const FIELD_LABELS = { LDAP: 'connections.ldap', DATABASE: 'connections.dbp' };

const when = (iso) => (iso ? formatDateTime(iso) : t('common.none'));
const tech = (text) => h('bdi', { class: 'conn-tech', dir: 'ltr', text });  // server names, codes, messages
// A label that may not exist (an example, a hint): nothing instead of the key.
const maybe = (key) => { const s = t(key); return s === key ? null : s; };

// ---- typing the password again ------------------------------------------------------------------------------------
function askPassword() {
  return new Promise((resolve) => {
    let confirmed = false;
    const input = h('input', { type: 'password', class: 'input', id: 'conn-reauth', autocomplete: 'current-password', dir: 'ltr' });
    const error = h('div', { class: 'error', role: 'alert' });
    const ok = h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.reauth.confirm') });
    const cancel = h('button', { type: 'button', class: 'btn', text: t('common.cancel') });
    const modal = openModal({
      title: t('connections.reauth.title'), size: 'sm', footer: [cancel, ok], onClose: () => resolve(confirmed),
      body: h('div', {}, h('p', { text: t('connections.reauth.intro') }),
        h('div', { class: 'field' }, h('label', { for: 'conn-reauth', text: t('connections.reauth.password') }), input, error)),
    });
    async function submit() {
      if (!input.value) return;
      ok.disabled = true;
      error.textContent = '';
      try {
        await api.post('/connections/reauth', { password: input.value });
        confirmed = true;
        modal.close(true);
      } catch (e) {
        error.textContent = e.message;
        input.select();
      } finally { ok.disabled = false; }
    }
    ok.addEventListener('click', submit);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    cancel.addEventListener('click', () => modal.close(true));
    input.focus();
  });
}

// What sensitive() answers when the password prompt was cancelled: nothing was done.
const NOT_CONFIRMED = Symbol('not confirmed');

async function sensitive(step) {
  try {
    return await step();
  } catch (error) {
    if (!(error instanceof ApiError) || error.code !== 'REAUTH_REQUIRED') throw error;
    if (!(await askPassword())) return NOT_CONFIRMED;
    return step();
  }
}

// Runs a step with its toast. Answers null when it was not done, else its answer (true for a 204).
async function run(step, okMessage) {
  try {
    const result = await sensitive(step);
    if (result === NOT_CONFIRMED) return null;
    if (okMessage) toast(okMessage);
    return result ?? true;
  } catch (error) {
    if (!error || error.status !== 401) toast((error && error.message) || t('errors.generic'), true);
    return null;
  }
}

function stateBadges(profile) {
  return h('span', { class: 'conn-badges' },
    badge(STATE_COLOR[profile.state] || 'grey', t(`connections.state.${profile.state}`)),
    badge(HEALTH_COLOR[profile.health] || 'grey', t(`connections.health.${profile.health}`)));
}

function facts(rows) {
  return h('dl', { class: 'dl' }, rows.filter(Boolean).map(([label, value]) =>
    h('div', {}, h('dt', { text: label }), h('dd', {}, value ?? t('common.none')))));
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast(t('connections.cutover.copied')); } catch { toast(t('connections.cutover.copyFailed'), true); }
}

// ---- the tabs -----------------------------------------------------------------------------------------------------
export async function renderConnections(body, tab, reload) {
  if (tab === 'signIn') return signInTab(body, reload);
  if (tab === 'database') return databaseTab(body, reload);
  if (tab === 'network') return networkTab(body, reload);
  return logTab(body, 0);
}

async function details(kind) {
  const list = await api.get('/connections/profiles', { kind });
  return Promise.all(list.items.map((p) => api.get(`/connections/profiles/${p.id}`)));
}

// ---- Sign-in and the company directory -------------------------------------------------------------------------------
async function signInTab(body, reload) {
  const [signIn, profiles, certs] = await Promise.all([api.get('/connections/sign-in'), details('LDAP'), api.get('/connections/certificates')]);
  async function importEnv() {
    const result = await run(() => api.post('/connections/import-env'));
    if (result) { toast(t(result.created ? 'connections.ldap.imported' : 'connections.ldap.alreadyImported')); reload(); }
  }
  replace(body, h('div', { class: 'stack' },
    signInCard(signIn, reload),
    card(t('connections.ldap.title'), h('div', {},
      h('p', { class: 'muted', text: t('connections.ldap.intro') }),
      profiles.length ? profiles.map((p) => connectionEditor(p, certs.items, reload)) : h('p', { class: 'muted', text: t('connections.ldap.empty') })),
    { actions: h('div', { class: 'actions' },
      signIn.envDirectory && !profiles.length ? h('button', { type: 'button', class: 'btn', text: t('connections.ldap.importEnv'), onclick: importEnv }) : null,
      h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.ldap.add'),
        onclick: () => addConnection('LDAP', ['ldap'], 'SIGN_IN', reload) })) })));
}

function signInCard(s, reload) {
  const choice = h('select', { id: 'conn-sign-in', class: 'select' },
    s.options.map((m) => h('option', { value: m, text: t(`connections.signIn.methods.${m}`) })));
  choice.value = s.method;
  const checks = [
    [t('connections.signIn.directoryReady'), s.directoryReady, s.method !== 'ldap'],
    [t('connections.signIn.breakGlassReady', { name: s.breakGlass.username || t('common.none') }), s.breakGlass.ready, !s.breakGlassRequired],
  ];
  async function apply() {
    if (choice.value === s.method && s.source === 'SETTINGS') return;
    const ok = await confirmDialog({ title: t('connections.signIn.confirmTitle'), body: t(`connections.signIn.confirm.${choice.value}`),
      confirmLabel: t('connections.signIn.apply') });
    if (!ok) return;
    if (await run(() => api.put('/connections/sign-in', { method: choice.value, version: s.version ?? undefined }), t('connections.signIn.done'))) reload();
  }
  return card(t('connections.signIn.title'), h('div', {},
    h('p', {}, `${t('connections.signIn.current')} `, h('strong', { text: t(`connections.signIn.methods.${s.method}`) }), ' ',
      badge('grey', t(`connections.source.${s.source}`))),
    h('ul', { class: 'conn-checks' }, checks.map(([text, ok, optional]) => h('li', {},
      badge(ok ? 'green' : (optional ? 'grey' : 'amber'), ok ? t('connections.signIn.ok') : (optional ? t('connections.signIn.recommended') : t('connections.signIn.missing'))),
      ' ', h('span', { text })))),
    h('div', { class: 'conn-inline' },
      h('div', { class: 'field' }, h('label', { for: 'conn-sign-in', text: t('connections.signIn.choose') }), choice),
      h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.signIn.apply'), onclick: apply })),
    h('p', { class: 'muted small' }, `${t('connections.signIn.recovery')} `, tech('flask --app wsgi settings-recover --as <admin> --sign-in local'))));
}

async function addConnection(kind, providers, purpose, reload) {
  const L = FIELD_LABELS[kind];
  formDialog({
    title: t(`${L}.newTitle`), size: 'md', values: { provider: providers[0], name: t(`${L}.defaultName`) },
    spec: [
      providers.length > 1 ? { key: 'provider', label: t(`${L}.provider`), type: 'select', required: true,
        options: providers.map((id) => ({ value: id, label: t(`connections.db.engineNames.${id}`) })) } : null,
      { key: 'name', label: t('connections.profile.name'), required: true, max: 80, span: true },
      { key: 'description', label: t('connections.profile.description'), type: 'textarea', max: 500, span: true },
    ].filter(Boolean),
    submit: (v) => api.post('/connections/profiles', { kind, provider: v.provider || providers[0], purpose, name: v.name, description: v.description || null }),
    onSaved: reload,
  });
}

// ---- one connection: its state, the draft form, tests, apply and the other actions --------------------------------
// The database is "staged for restart" in place of applied, has no on/off switch, and shows its cutover steps.
function connectionEditor(initial, certs, reload) {
  let profile = initial;
  const schema = profile.schema;
  const L = FIELD_LABELS[profile.kind];
  const isLdap = profile.kind === 'LDAP';
  const staged = schema.restartRequired;
  const source = profile.draft || profile.active;
  const values = { ...((source && source.fields) || {}) };
  const secrets = {};  // name -> { action, value }
  const fieldErrors = new Map();
  let dirty = false;
  const prefix = `conn-${profile.id}`;

  function control(field) {
    const id = `${prefix}-${field.name}`;
    const error = h('span', { class: 'error', id: `${id}-error` });
    fieldErrors.set(field.name, error);
    let input;
    if (field.type === 'choice') {
      input = h('select', { id, class: 'select', dir: 'ltr' }, field.choices.map((c) => h('option', { value: c, text: t(`${L}.choices.${c}`) })));
      input.value = values[field.name] ?? field.default ?? '';
      input.addEventListener('change', () => { values[field.name] = input.value; dirty = true; });
    } else if (field.type === 'certs') {
      const chosen = new Set((values[field.name] || []).map(String));
      input = h('div', { id, class: 'conn-certs', role: 'group' },
        certs.length ? certs.map((c) => {
          const box = h('input', { type: 'checkbox', id: `${id}-${c.id}`, value: c.id, checked: chosen.has(c.id) || undefined });
          box.addEventListener('change', () => {
            if (box.checked) chosen.add(c.id); else chosen.delete(c.id);
            values[field.name] = [...chosen];
            dirty = true;
          });
          return h('label', { class: 'conn-check', for: `${id}-${c.id}` }, box, ' ', h('bdi', { text: c.name }), ' ',
            badge(CERT_COLOR[c.state] || 'grey', t(`connections.cert.state.${c.state}`)));
        }) : h('p', { class: 'muted small', text: t('connections.ldap.noCerts') }));
    } else {
      const isList = field.type === 'hosts';
      input = h('input', { id, class: 'input', dir: 'ltr', type: field.type === 'int' ? 'number' : 'text', spellcheck: 'false',
        autocomplete: 'off', placeholder: maybe(`${L}.examples.${field.name}`) || undefined,
        min: field.low ?? undefined, max: field.high ?? undefined, maxlength: field.type === 'int' ? undefined : field.maxLength });
      const current = values[field.name];
      input.value = current === undefined || current === null ? '' : (isList ? current.join(', ') : String(current));
      input.addEventListener('input', () => {
        const raw = input.value.trim();
        values[field.name] = isList ? raw.split(',').map((x) => x.trim()).filter(Boolean) : (field.type === 'int' && raw ? Number(raw) : raw);
        dirty = true;
      });
    }
    const hint = maybe(`${L}.hints.${field.name}`);
    return h('div', { class: 'field' },
      field.type === 'certs' ? h('span', { class: 'label', text: t(`${L}.fields.${field.name}`) + (field.required ? ' *' : '') })
        : h('label', { for: id, text: t(`${L}.fields.${field.name}`) + (field.required ? ' *' : '') }),
      input, hint ? h('span', { class: 'muted small', text: hint }) : null, error);
  }

  function secretControl(spec) {
    const saved = source && source.secrets && source.secrets[spec.name];
    const holder = h('div', { class: 'conn-secret' });
    const error = h('span', { class: 'error' });
    fieldErrors.set(`secrets.${spec.name}`, error);
    function paint() {
      const change = secrets[spec.name];
      if (change && change.action === 'replace') {
        const input = h('input', { id: `${prefix}-${spec.name}`, type: 'password', class: 'input', dir: 'ltr', autocomplete: 'new-password' });
        input.value = change.value || '';
        input.addEventListener('input', () => { change.value = input.value; dirty = true; });
        replace(holder, input, h('button', { type: 'button', class: 'btn btn-sm', text: t('common.cancel'), onclick: () => { delete secrets[spec.name]; paint(); } }));
        input.focus();
      } else if (change && change.action === 'clear') {
        replace(holder, badge('amber', t('connections.secret.willClear')),
          h('button', { type: 'button', class: 'btn btn-sm', text: t('common.cancel'), onclick: () => { delete secrets[spec.name]; paint(); } }));
      } else {
        replace(holder,
          badge(saved && saved.configured ? 'green' : 'grey', saved && saved.configured ? t('connections.secret.configured') : t('connections.secret.notSet')),
          saved && saved.configured && !saved.keyKnown ? badge('red', t('connections.secret.keyUnknown')) : null,
          h('button', { type: 'button', class: 'btn btn-sm', text: saved && saved.configured ? t('connections.secret.replace') : t('connections.secret.set'),
            onclick: () => { secrets[spec.name] = { action: 'replace', value: '' }; dirty = true; paint(); } }),
          saved && saved.configured ? h('button', { type: 'button', class: 'btn btn-sm', text: t('connections.secret.clear'),
            onclick: () => { secrets[spec.name] = { action: 'clear' }; dirty = true; paint(); } }) : null);
      }
    }
    paint();
    return h('div', { class: 'field' },
      h('span', { class: 'label', text: t(`${L}.secrets.${spec.name}`) + (spec.required ? ' *' : '') }),
      holder, h('span', { class: 'muted small', text: t('connections.secret.hint') }), error);
  }

  function showErrors(error) {
    for (const el of fieldErrors.values()) el.textContent = '';
    let shown = false;
    for (const fe of (error && error.fieldErrors) || []) {
      const key = fe.field.startsWith('fields.') ? fe.field.slice(7) : fe.field;
      const el = fieldErrors.get(key);
      if (el) { el.textContent = fe.message; shown = true; }
    }
    if (!shown) toast((error && error.message) || t('errors.generic'), true);
  }

  async function saveDraft() {
    const payload = { fields: values, secrets: Object.fromEntries(Object.entries(secrets).filter(([, c]) => c.action !== 'keep')) };
    if (profile.draft) payload.draftVersion = profile.draft.version;
    try {
      if (await sensitive(() => api.put(`/connections/profiles/${profile.id}/draft`, payload)) === NOT_CONFIRMED) return;
      toast(t('connections.draft.saved'));
      reload();
    } catch (error) {
      if (error && error.status !== 401) showErrors(error);
    }
  }

  // Test: the saved draft (default), or the active revision when there is no draft.
  const sampleUser = h('input', { id: `${prefix}-sample`, class: 'input', dir: 'ltr', autocomplete: 'off', spellcheck: 'false',
    placeholder: t('connections.test.sampleExample') });
  const samplePassword = h('input', { id: `${prefix}-sample-password`, type: 'password', class: 'input', dir: 'ltr', autocomplete: 'off' });
  const results = h('div', { class: 'conn-results', 'aria-live': 'polite' });

  function stageList(items) {
    return h('ol', { class: 'conn-stages' }, items.map((r) => h('li', {},
      badge(OUTCOME_COLOR[r.outcome] || 'grey', t(`connections.outcome.${r.outcome}`)), ' ',
      h('strong', { text: t(`connections.stage.${r.stage}`) }),
      r.latencyMs !== null && r.latencyMs !== undefined ? h('span', { class: 'muted small', text: ` ${t('connections.test.ms', { n: r.latencyMs })}` }) : null,
      r.message ? h('div', { class: 'small' }, tech(r.message)) : null,
      r.hint ? h('div', { class: 'small muted' }, tech(r.hint)) : null)));
  }

  async function test() {
    if (dirty) { toast(t('connections.test.saveFirst'), true); return; }
    const target = profile.draft ? 'draft' : 'active';
    replace(results, h('p', { class: 'muted', text: t('connections.test.running') }));
    try {
      const answer = await api.post(`/connections/profiles/${profile.id}/test`, isLdap
        ? { target, sample: { username: sampleUser.value.trim() || null, password: samplePassword.value || null } } : { target });
      samplePassword.value = '';  // used once
      replace(results, stageList(answer.results));
      profile = answer.profile;
      paintState();
    } catch (error) {
      replace(results);
      if (error && error.status !== 401) showErrors(error);
    }
  }

  async function apply() {
    if (dirty) { toast(t('connections.test.saveFirst'), true); return; }
    const words = staged ? 'connections.staging' : 'connections.apply';
    const ok = await confirmDialog({ title: t(`${words}.title`), body: t(`${words}.body`, { name: profile.name }), confirmLabel: t(`${words}.button`) });
    if (!ok) return;
    if (await run(() => api.post(`/connections/profiles/${profile.id}/apply`, { draftVersion: profile.draft.version, version: profile.version }),
      t(`${words}.done`))) reload();
  }

  async function discard() {
    const ok = await confirmDialog({ title: t('connections.draft.discardTitle'), body: t('connections.draft.discardBody'),
      confirmLabel: t('connections.draft.discard'), danger: true });
    if (ok && await run(() => api.post(`/connections/profiles/${profile.id}/draft/discard`, { version: profile.draft.version }), t('connections.draft.discarded'))) reload();
  }

  async function toggle() {
    const action = profile.enabled ? 'disable' : 'enable';
    if (await run(() => api.post(`/connections/profiles/${profile.id}/${action}`, { version: profile.version }), t(`connections.profile.${action}d`))) reload();
  }

  async function remove() {
    const ok = await confirmDialog({ title: t('connections.profile.deleteTitle'), body: t('connections.profile.deleteBody', { name: profile.name }),
      confirmLabel: t('connections.profile.delete'), danger: true });
    if (ok && await run(() => api.del(`/connections/profiles/${profile.id}`, { version: profile.version }), t('connections.profile.deleted'))) reload();
  }

  async function rollback(revision) {
    if (await run(() => api.post(`/connections/profiles/${profile.id}/rollback`, { revisionId: revision.id, version: profile.version }),
      t('connections.revisions.copied', { n: revision.revisionNo }))) reload();
  }

  const stateLine = h('div', { class: 'conn-state' });
  function paintState() {
    const draft = profile.draft;
    const blockers = (draft && draft.blockers) || [];
    replace(stateLine,
      stateBadges(profile),
      profile.inUse.includes('SIGN_IN') ? badge('amber', t('connections.profile.inUse')) : null,
      h('span', { class: 'muted small', text: profile.activeRevisionNo
        ? t(staged ? 'connections.profile.stagedSince' : 'connections.profile.activeSince', { n: profile.activeRevisionNo, date: when(profile.activeSince), name: profile.activeBy || '' })
        : t('connections.profile.neverActive') }),
      draft ? h('span', { class: 'muted small', text: t('connections.draft.line', { n: draft.revisionNo, date: when(draft.updatedAt), name: draft.updatedBy || '' }) }) : null,
      draft && blockers.length ? h('span', { class: 'small' }, `${t('connections.apply.notYet')} `,
        blockers.map((b) => badge('amber', t(`connections.blockers.${b}`)))) : null);
  }
  paintState();

  const basic = schema.fields.filter((f) => !f.advanced);
  const advanced = schema.fields.filter((f) => f.advanced);
  if (source && source.tests && source.tests.length) replace(results, h('p', { class: 'small muted', text: t('connections.test.last') }), stageList(source.tests));

  return h('article', { class: 'conn-profile' },
    h('div', { class: 'conn-head' }, h('h3', {}, h('bdi', { text: profile.name })),
      h('div', { class: 'actions' },
        profile.activeRevisionNo && !staged ? h('button', { type: 'button', class: 'btn btn-sm', onclick: toggle,
          text: profile.enabled ? t('connections.profile.disable') : t('connections.profile.enable') }) : null,
        profile.enabled || profile.inUse.length ? null : h('button', { type: 'button', class: 'btn btn-sm btn-danger', text: t('connections.profile.delete'), onclick: remove }))),
    profile.description ? h('p', { class: 'muted small', dir: 'auto', text: profile.description }) : null,
    stateLine,
    h('div', { class: 'form-grid' }, basic.map(control), schema.secrets.map(secretControl)),
    advanced.length ? h('details', { class: 'conn-advanced' }, h('summary', { text: t('connections.advanced') }),
      h('div', { class: 'form-grid' }, advanced.map(control))) : null,
    isLdap ? h('p', { class: 'muted small', text: t('connections.ldap.rolesNote') }) : null,
    h('div', { class: 'actions' },
      h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.draft.save'), onclick: saveDraft }),
      profile.draft ? h('button', { type: 'button', class: 'btn', text: t('connections.draft.discard'), onclick: discard }) : null),
    h('fieldset', { class: 'conn-test' },
      h('legend', { text: t('connections.test.title') }),
      h('p', { class: 'muted small', text: t(isLdap ? 'connections.test.intro' : 'connections.dbp.testIntro') }),
      h('div', { class: 'conn-inline' },
        isLdap ? h('div', { class: 'field' }, h('label', { for: sampleUser.id, text: t('connections.test.sampleUser') }), sampleUser) : null,
        isLdap ? h('div', { class: 'field' }, h('label', { for: samplePassword.id, text: t('connections.test.samplePassword') }), samplePassword) : null,
        h('button', { type: 'button', class: 'btn', text: profile.draft ? t('connections.test.runDraft') : t('connections.test.runActive'), onclick: test }),
        profile.draft ? h('button', { type: 'button', class: 'btn btn-primary', text: t(staged ? 'connections.staging.button' : 'connections.apply.button'), onclick: apply }) : null),
      results),
    staged && profile.cutover && profile.state === 'STAGED' ? cutoverCard(profile) : null,
    profile.revisions && profile.revisions.length > 1 ? h('details', { class: 'conn-advanced' }, h('summary', { text: t('connections.revisions.title') }),
      h('ul', { class: 'conn-list' }, profile.revisions.map((r) => h('li', {},
        h('span', { text: t('connections.revisions.line', { n: r.revisionNo, date: when(r.updatedAt), name: r.updatedBy || '' }) }), ' ',
        badge(r.state === 'ACTIVE' ? 'green' : 'grey', t(`connections.revisions.state.${r.state}`)), ' ',
        r.state === 'SUPERSEDED' && !profile.draft ? h('button', { type: 'button', class: 'btn btn-sm', text: t('connections.revisions.copy'), onclick: () => rollback(r) }) : null)))) : null);
}

// ---- the main database: the one in use (read-only, from the server file) and candidates for a planned restart ----
async function databaseTab(body, reload) {
  const [status, profiles, certs] = await Promise.all([api.get('/connections/database'), details('DATABASE'), api.get('/connections/certificates')]);
  const r = status.running;
  const target = r.engine === 'sqlite'
    ? [[t('connections.db.file'), tech(r.target.file)]]
    : [[t('connections.db.dsn'), tech(r.target.dsn || '')], [t('connections.db.user'), tech(r.target.user || '')],
      r.target.schema ? [t('connections.db.schema'), tech(r.target.schema)] : null];
  const matching = profiles.find((p) => p.id === r.matchesProfile);
  const demo = r.demoAccounts
    ? h('span', {}, badge('amber', t('connections.db.demoYes', { n: r.demoAccounts })), ' ', h('span', { class: 'muted small', text: t('connections.db.demoNote') }))
    : badge('green', t('connections.db.demoNo'));
  replace(body, h('div', { class: 'stack' },
    card(t('connections.db.title'), h('div', {},
      facts([
        [t('connections.db.engine'), t(`connections.db.engineNames.${r.engine}`)],
        ...target,
        [t('connections.db.schemaVersion'), r.engine === 'sqlite'
          ? t('connections.db.versionOf', { have: r.schemaVersion ?? t('common.none'), want: r.expectedVersion })
          : t('connections.db.checkedAtStart', { want: r.expectedVersion })],
        [t('connections.db.health'), badge(HEALTH_COLOR[r.health] || 'grey', t(`connections.health.${r.health}`))],
        r.latencyMs !== null ? [t('connections.db.latency'), t('connections.test.ms', { n: r.latencyMs })] : null,
        r.pool ? [t('connections.db.pool'), t('connections.db.poolLine', { used: r.pool.inUse, size: r.pool.size })] : null,
        r.serverVersion ? [t('connections.db.serverVersion'), tech(r.serverVersion)] : null,
        [t('connections.db.demoData'), demo],
        [t('connections.db.source'), t('connections.db.fromEnv')],
        matching ? [t('connections.db.matches'), h('bdi', { text: matching.name })] : null,
        r.error ? [t('connections.db.error'), tech(r.error)] : null,
      ]),
      h('p', { class: 'muted small', text: t('connections.db.bootstrap') }))),
    card(t('connections.dbp.title'), h('div', {},
      h('p', { class: 'muted', text: t('connections.dbp.intro') }),
      h('p', { class: 'conn-clean' }, badge('green', t('connections.dbp.cleanBadge')), ' ', h('span', { text: t('connections.dbp.clean') })),
      profiles.length ? profiles.map((p) => connectionEditor(p, certs.items, reload)) : h('p', { class: 'muted', text: t('connections.dbp.empty') })),
    { actions: h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.dbp.add'),
      onclick: () => addConnection('DATABASE', status.providers, 'PRIMARY', reload) }) })));
}

// The planned restart, step by step, with the lines for the server file (never the password).
function cutoverCard(profile) {
  const lines = profile.cutover.envLines.join('\n');
  const version = `V${String(profile.cutover.expectedVersion).padStart(3, '0')}`;
  const steps = ['prepare', 'retest', 'backup', 'stop', 'env', 'start', 'setup', 'directory'];
  return h('section', { class: 'conn-cutover' },
    h('h4', { text: t('connections.cutover.title') }),
    h('ol', { class: 'conn-steps' }, steps.map((k) => h('li', {}, t(`connections.cutover.steps.${k}`, { version }),
      k === 'setup' ? h('div', {}, tech(profile.cutover.setupCommand)) : null,
      k === 'env' ? h('div', { class: 'conn-env' }, h('pre', { dir: 'ltr', class: 'conn-tech', text: lines }),
        h('button', { type: 'button', class: 'btn btn-sm', text: t('connections.cutover.copy'), onclick: () => copyText(lines) })) : null))),
    h('p', { class: 'muted small', text: t('connections.cutover.back') }));
}

// ---- trusted certificates and approved destinations --------------------------------------------------------------------
async function networkTab(body, reload) {
  const [certs, rules] = await Promise.all([api.get('/connections/certificates'), api.get('/connections/destinations')]);
  const certName = h('input', { id: 'cert-name', class: 'input', maxlength: 80, dir: 'ltr', placeholder: t('connections.cert.nameExample') });
  const certFile = h('input', { id: 'cert-file', type: 'file', class: 'input', accept: '.pem,.cer,.crt,.der' });
  async function upload() {
    if (!certFile.files.length) { toast(t('connections.cert.chooseFile'), true); return; }
    const send = () => {
      const form = new FormData();
      form.append('name', certName.value.trim());
      form.append('file', certFile.files[0], certFile.files[0].name);
      return request('POST', '/connections/certificates', { form });
    };
    const result = await run(send, t('connections.cert.uploaded'));
    if (result) {
      if (result.warning) toast(result.warning, true);
      reload();
    }
  }
  async function removeCert(c) {
    const ok = await confirmDialog({ title: t('connections.cert.deleteTitle'), body: c.name, confirmLabel: t('connections.profile.delete'), danger: true });
    if (ok && await run(() => api.del(`/connections/certificates/${c.id}`, { version: c.version }), t('connections.cert.deleted'))) reload();
  }
  function editRule(rule) {
    formDialog({
      title: rule ? t('connections.dest.editTitle') : t('connections.dest.newTitle'), size: 'md',
      values: rule ? { host: rule.host, port: rule.port, purpose: rule.purpose, note: rule.note } : { port: 636, purpose: 'LDAP' },
      spec: [
        { key: 'host', label: t('connections.dest.host'), required: true, max: 253, dir: 'ltr', span: true },
        { key: 'port', label: t('connections.dest.port'), type: 'number', step: 1, required: true },
        { key: 'purpose', label: t('connections.dest.purpose'), type: 'select', required: true,
          options: ['LDAP', 'DATABASE'].map((p) => ({ value: p, label: t(`connections.dest.purposes.${p}`) })) },
        { key: 'note', label: t('connections.dest.note'), max: 500, span: true },
      ],
      submit: async (v) => {
        const payload = { host: v.host, port: Number(v.port), purpose: v.purpose, note: v.note || null };
        const answer = await sensitive(() => (rule ? api.patch(`/connections/destinations/${rule.id}`, { ...payload, version: rule.version })
          : api.post('/connections/destinations', payload)));
        if (answer === NOT_CONFIRMED) throw new Error(t('connections.reauth.notConfirmed'));
        return answer;
      },
      onSaved: reload,
    });
  }
  async function removeRule(rule) {
    const ok = await confirmDialog({ title: t('connections.dest.deleteTitle'), body: `${rule.host}:${rule.port}`, confirmLabel: t('connections.profile.delete'), danger: true });
    if (ok && await run(() => api.del(`/connections/destinations/${rule.id}`, { version: rule.version }), t('connections.dest.deleted'))) reload();
  }
  replace(body, h('div', { class: 'stack' },
    card(t('connections.cert.title'), h('div', {},
      h('p', { class: 'muted', text: t('connections.cert.intro') }),
      certs.items.length ? dataTable([
        { key: 'name', label: t('connections.cert.name'), render: (c) => h('bdi', { text: c.name }) },
        { key: 'state', label: t('connections.cert.stateLabel'), render: (c) => badge(CERT_COLOR[c.state] || 'grey', t(`connections.cert.state.${c.state}`)) },
        { key: 'until', label: t('connections.cert.until'), render: (c) => when(c.notAfter) },
        { key: 'subject', label: t('connections.cert.subject'), render: (c) => h('span', { class: 'small' }, tech(c.subject)) },
        { key: 'used', label: t('connections.cert.usedBy'), render: (c) => c.usedBy.join(', ') || t('common.none') },
        { key: 'del', label: '', render: (c) => (c.usedBy.length ? null : h('button', { type: 'button', class: 'btn btn-sm', text: t('connections.profile.delete'), onclick: () => removeCert(c) })) },
      ], certs.items) : h('p', { class: 'muted', text: t('connections.cert.empty') }),
      h('div', { class: 'conn-inline' },
        h('div', { class: 'field' }, h('label', { for: 'cert-name', text: t('connections.cert.name') }), certName),
        h('div', { class: 'field' }, h('label', { for: 'cert-file', text: t('connections.cert.file') }), certFile),
        h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.cert.upload'), onclick: upload })))),
    card(t('connections.dest.title'), h('div', {},
      h('p', { class: 'muted', text: t('connections.dest.intro') }),
      rules.items.length ? dataTable([
        { key: 'host', label: t('connections.dest.host'), render: (r) => tech(r.host) },
        { key: 'port', label: t('connections.dest.port'), num: true, render: (r) => String(r.port) },
        { key: 'purpose', label: t('connections.dest.purpose'), render: (r) => t(`connections.dest.purposes.${r.purpose}`) },
        { key: 'note', label: t('connections.dest.note'), render: (r) => r.note },
        { key: 'act', label: '', render: (r) => h('div', { class: 'row-actions' },
          h('button', { type: 'button', class: 'btn btn-sm', text: t('common.edit'), onclick: () => editRule(r) }),
          h('button', { type: 'button', class: 'btn btn-sm', text: t('connections.profile.delete'), onclick: () => removeRule(r) })) },
      ], rules.items) : h('p', { class: 'muted', text: t('connections.dest.empty') })),
    { actions: h('button', { type: 'button', class: 'btn btn-primary', text: t('connections.dest.add'), onclick: () => editRule(null) }) })));
}

// ---- history and diagnostics ---------------------------------------------------------------------------------------
async function logTab(body, page) {
  const [history, d] = await Promise.all([api.get('/connections/history', { page, size: 50 }), api.get('/connections/diagnostics')]);
  const why = t('connections.diag.bootstrapWhy');
  replace(body, h('div', { class: 'stack' },
    card(t('connections.history.title'), h('div', {},
      dataTable([
        { key: 'at', label: t('connections.history.when'), render: (e) => when(e.at) },
        { key: 'actor', label: t('connections.history.who'), render: (e) => e.actor },
        { key: 'action', label: t('connections.history.action'), render: (e) => t(`connections.history.actions.${e.action}`) },
        { key: 'what', label: t('connections.history.what'), render: (e) => h('span', {}, t(`connections.history.entities.${e.entityType}`),
          e.name ? h('span', {}, ' ', h('bdi', { text: e.name })) : null) },
        { key: 'changed', label: t('connections.history.changed'), render: (e) => (e.changed.length ? h('span', { class: 'small' }, tech(e.changed.join(', '))) : null) },
        { key: 'reason', label: t('connections.history.reason'), render: (e) => e.reason },
      ], history.items, { empty: t('connections.history.empty') }),
      history.totalPages > 1 ? pager({ page: history.page, totalPages: history.totalPages, totalItems: history.totalItems,
        onPage: (p) => logTab(body, p) }) : null)),
    card(t('connections.diag.title'), h('div', {},
      facts([
        [t('connections.diag.settingsKey'), d.settingsKey.configured ? tech(d.settingsKey.keyId) : t('connections.diag.noKey')],
        d.settingsKey.previousKeys ? [t('connections.diag.previousKeys'), String(d.settingsKey.previousKeys)] : null,
        [t('connections.diag.generation'), String(d.generation)],
        [t('connections.diag.rollout'), t(`connections.diag.rollouts.${d.rollout}`)],
        [t('connections.diag.directorySource'), t(`connections.source.${d.sources.directory || 'NONE'}`)],
        [t('connections.diag.signInSource'), t(`connections.source.${d.sources.signIn || 'ENV'}`)],
        d.thisProcess.error ? [t('connections.db.error'), tech(d.thisProcess.error)] : null,
      ]),
      h('h4', { text: t('connections.diag.bootstrap') }),
      h('p', { class: 'muted small', text: t('connections.diag.bootstrapIntro') }),
      h('ul', { class: 'conn-list' }, d.bootstrap.map((b, i) => h('li', {}, tech(b.name),
        h('span', { class: 'muted small', text: ` ${(Array.isArray(why) && why[i]) || b.why}` }))))))));
}
