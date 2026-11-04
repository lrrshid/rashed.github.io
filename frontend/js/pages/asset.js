// Individual capability profile: one asset with its acquisition, contract, warranty, readiness dimensions, status
// history and full audit trail. Tests, maintenance, projects and documents tabs fill in as those modules arrive.
import { api } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate, formatDateTime, formatMoney, formatNumber, formatPercent } from '../lib/format.js';
import { card, categoryGlyph, dl, errorBox, historyList, loadingBox, meter, refName, statusBadge, tabs, toast } from '../components/ui.js';
import { confirmDialog } from '../components/modal.js';
import { openAssetForm } from './forms.js';
import { fieldLabel } from './field-labels.js';

export async function render(container, ctx) {
  let tab = ctx.query.tab || 'overview';
  async function load() {
    replace(container, loadingBox());
    let asset;
    try {
      asset = await api.get(`/assets/${ctx.params.id}`);
    } catch (error) {
      replace(container, errorBox(error, load));
      return;
    }
    const actions = h('div', { class: 'actions' });
    if (canEdit('edit.assets')) {
      actions.append(h('button', { type: 'button', class: 'btn btn-primary', onclick: () => openAssetForm(asset, load) }, icon('edit'), t('common.edit')));
      actions.append(h('button', { type: 'button', class: 'btn', onclick: async () => {
        const archiving = !asset.archived;
        if (archiving && !(await confirmDialog({ title: t('common.archive'), body: `${asset.code}`, confirmLabel: t('common.archive'), danger: true }))) return;
        try { await api.post(`/assets/${asset.id}/archive`, { archived: archiving, version: asset.version }); toast(t('common.saved')); load(); } catch (e) { toast(e.message, true); }
      } }, icon(asset.archived ? 'restore' : 'archive'), asset.archived ? t('common.restore') : t('common.archive')));
    }
    const header = h('div', { class: 'card' }, h('div', { class: 'profile-head' },
      icon(categoryGlyph(asset.category && asset.category.code), 'profile-glyph'),
      h('div', { class: 'profile-main' },
        h('div', { class: 'breadcrumb' }, h('a', { href: '/capabilities', text: t('nav.capabilities') }), ' › ',
          asset.category ? h('a', { href: `/capabilities/category/${asset.category.code}`, text: asset.category.code }) : null, ' › ',
          asset.model ? h('a', { href: `/models/${asset.model.id}`, text: refName(asset.model) }) : null),
        h('h1', { tabindex: '-1' }, h('span', { class: 'mono', text: asset.code }), ` · ${refName(asset.model)}`),
        h('div', { class: 'actions' }, statusBadge('ASSET', asset.status), asset.archived ? h('span', { class: 'badge c-grey', text: t('common.archived') }) : null,
          h('span', { class: 'muted small', text: `${t('fields.updatedAt')}: ${formatDateTime(asset.updatedAt)}` })),
        h('div', { class: 'section-label' }),
        dl([
          [t('fields.department'), refName(asset.department)], [t('fields.category'), refName(asset.category)],
          [t('fields.serial'), asset.serialNumber ? h('span', { class: 'mono', text: asset.serialNumber }) : null],
          [t('fields.site'), refName(asset.site)], [t('fields.manufacturer'), refName(asset.manufacturer)],
          [t('fields.opReadiness'), asset.readiness.operational === null ? null : formatPercent(asset.readiness.operational)],
          [t('fields.overallReadiness'), asset.readiness.overall === null ? null : formatPercent(asset.readiness.overall)],
          [t('fields.responsible'), name(asset, 'responsible')],
        ])),
      actions));

    const tabBar = tabs(['overview', 'acquisition', 'readiness', 'history', 'tests', 'maintenance', 'activity'].map((k) => ({ key: k, label: t(`asset.tabs.${k}`) })), tab, (k) => { tab = k; ctx.setQuery({ tab: k }); load(); });
    const body = h('div', { class: 'stack' });
    replace(container, header, h('div', { class: 'section-label' }), tabBar, body);

    if (tab === 'overview' || tab === 'acquisition') {
      body.append(card(t('asset.tabs.acquisition'), dl([
        [t('fields.acquisitionDate'), formatDate(asset.acquisitionDate)],
        [t('fields.deliveryDate'), formatDate(asset.expectedDeliveryDate)],
        [t('fields.acquisitionMethod'), asset.acquisitionMethod ? t(`methods.${asset.acquisitionMethod}`) : null],
        [t('fields.contract'), asset.contract ? `${asset.contract.code} · ${name(asset.contract, 'title')}` : null],
        [t('fields.supplier'), asset.contract ? refName(asset.contract.supplier) : null],
        [t('fields.unitValue'), formatMoney(asset.unitValue)],
        [t('fields.warranty'), asset.warrantyEndDate ? `${formatDate(asset.warrantyEndDate)} · ${asset.warrantyActive ? t('warrantyStates.ACTIVE') : t('warrantyStates.EXPIRED')}` : null],
        [t('fields.serviceLife'), asset.serviceLifeYears ? t('common.years', { n: asset.serviceLifeYears }) : null],
        [t('fields.age'), asset.ageYears !== null ? t('common.years', { n: formatNumber(asset.ageYears, 1) }) : null],
        [t('fields.hours'), asset.operatingHours !== null ? formatCount(asset.operatingHours) : null],
      ])));
    }
    if (tab === 'overview' || tab === 'readiness') {
      const dims = [['operational', 'opReadiness'], ['technical', 'techReadiness'], ['mission', 'missionReadiness'], ['maintenance', 'maintReadiness']];
      body.append(card(t('fields.readiness'), h('div', { class: 'bar-rows' }, dims.map(([k, label]) => h('div', { class: 'bar-row' },
        h('span', { text: t(`fields.${label}`) }), meter(asset.readiness[k] ?? 0, undefined, true),
        h('span', { class: 'mono', text: asset.readiness[k] === null ? t('common.none') : formatPercent(asset.readiness[k]) })))),
      { foot: `${t('fields.overallReadiness')}: ${asset.readiness.overall === null ? t('common.none') : formatPercent(asset.readiness.overall)}` }));
    }
    if (tab === 'overview' && asset.notes) body.append(card(t('fields.notes'), h('p', { text: asset.notes })));
    if (tab === 'overview' || tab === 'history') {
      body.append(card(t('asset.tabs.history'), asset.statusHistory.length ? h('ul', { class: 'timeline' }, asset.statusHistory.map((s) =>
        h('li', {}, statusBadge('ASSET', s.status), ' ', formatDateTime(s.changedAt),
          s.readiness !== null ? h('span', { class: 'muted', text: ` · ${formatPercent(s.readiness)}` }) : null,
          s.note ? h('div', { class: 'muted small', text: s.note }) : null))) : h('div', { class: 'empty', text: t('history.empty') })));
    }
    if (tab === 'tests') {
      const data = await api.get('/tests', { asset: asset.id });
      const byModel = data.items.length ? data : await api.get('/tests', { model: asset.model.id });
      body.append(card(t('asset.tabs.tests'), h('ul', { class: 'timeline' }, byModel.items.map((e) => h('li', {},
        h('div', {}, h('strong', { class: 'mono', text: `${e.code} ` }), name(e, 'title'), ' ', statusBadge('TEST', e.status)),
        h('div', { class: 'muted small', text: `${formatDate(e.testDate)}${e.score !== null ? ` · ${e.score}/100` : ''}` }))))));
    }
    if (tab === 'maintenance') {
      const data = await api.get('/maintenance', { asset: asset.id });
      body.append(card(t('asset.tabs.maintenance'), data.items.length ? h('ul', { class: 'timeline' }, data.items.map((m) => h('li', {},
        h('div', {}, h('strong', { class: 'mono', text: `${m.code} ` }), name(m, 'title'), ' ', statusBadge('MAINTENANCE', m.status)),
        h('div', { class: 'muted small', text: `${formatDate(m.startDate)} → ${formatDate(m.actualEndDate || m.expectedEndDate)} · ${formatPercent(m.progressPct)}` }))))
        : h('div', { class: 'empty', text: t('history.empty') })));
    }
    if (tab === 'activity') {
      const box = h('div', {}, loadingBox());
      body.append(card(t('asset.tabs.activity'), box));
      try {
        const data = await api.get(`/history/ASSET/${asset.id}`);
        replace(box, historyList(data.items, fieldLabel));
      } catch (error) { replace(box, errorBox(error)); }
    }
  }
  await load();
}
