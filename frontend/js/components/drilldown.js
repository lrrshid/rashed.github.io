// "No static numbers": every figure opens the exact records behind it. A figure carries `drill` — the asset filters
// that reproduce it (the server builds them next to the figure) — and this dialog lists those assets.
import { api, download } from '../api.js';
import { h, icon, replace } from '../lib/dom.js';
import { canEdit, can, state } from '../lib/state.js';
import { name, t } from '../labels.js';
import { formatPercent } from '../lib/format.js';
import { openModal } from './modal.js';
import { dataTable, errorBox, loadingBox, pager, refName, statusBadge } from './ui.js';

export function assetColumns() {
  return [
    { key: 'code', label: t('fields.assetId'), sort: 'code', render: (a) => h('a', { href: `/assets/${a.id}`, class: 'mono', text: a.code }) },
    { key: 'model', label: t('fields.model'), sort: 'model', render: (a) => refName(a.model) },
    { key: 'category', label: t('fields.category'), render: (a) => (a.category ? a.category.code : null) },
    { key: 'department', label: t('fields.department'), sort: 'department', render: (a) => refName(a.department) },
    { key: 'status', label: t('fields.status'), sort: 'status', render: (a) => statusBadge('ASSET', a.status) },
    { key: 'op', label: t('fields.opReadiness'), num: true, sort: 'readiness', render: (a) => (a.readiness.operational === null ? null : formatPercent(a.readiness.operational)) },
    { key: 'overall', label: t('fields.overallReadiness'), num: true, render: (a) => (a.readiness.overall === null ? null : formatPercent(a.readiness.overall)) },
    { key: 'site', label: t('fields.site'), render: (a) => refName(a.site) },
  ];
}

export function withDepartment(filters) {
  const out = { ...filters };
  if (state.department && !out.department) out.department = [state.department];
  return out;
}

export function openDrill(title, filters) {
  const body = h('div', {}, loadingBox());
  let page = 0;
  const query = withDepartment(filters);
  async function load() {
    replace(body, loadingBox());
    try {
      const data = await api.get('/assets', { ...query, page, size: 25 });
      replace(body,
        h('p', { class: 'muted small', text: t('dashboard.drillCount', { n: data.totalItems }) }),
        dataTable(assetColumns(), data.items),
        pager({ page, totalPages: data.totalPages, totalItems: data.totalItems, onPage: (p) => { page = p; load(); } }));
    } catch (error) {
      replace(body, errorBox(error, load));
    }
  }
  const footer = [];
  if (can('export')) {
    footer.push(h('button', { type: 'button', class: 'btn', onclick: () => download('/assets.csv', { ...query, lang: document.documentElement.lang }) }, icon('download'), t('common.exportCsv')));
  }
  openModal({ title, body, footer, size: 'lg' });
  load();
}

export { canEdit, name };
