// Global search: one query across capabilities, serial numbers, projects, contracts, tests, maintenance and
// documents (GET /search). Each group lists its matches with a link to the record.
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { name, t } from '../labels.js';
import { card, dataTable, errorBox, loadingBox, refName, statusBadge } from '../components/ui.js';

const GROUPS = [
  ['models', 'registry.tabModels', (m) => [h('a', { href: `/models/${m.id}`, text: `${m.code} · ${name(m)}` }), refName(m.category), refName(m.manufacturer)]],
  ['assets', 'registry.tabAssets', (a) => [h('a', { href: `/assets/${a.id}`, class: 'mono', text: a.code }), a.serialNumber, refName(a.model), refName(a.department), statusBadge('ASSET', a.status)]],
  ['requirements', 'registry.tabRequirements', (r) => [h('a', { href: `/requirements/${r.id}`, text: `${r.code} · ${name(r)}` }), refName(r.department)]],
  ['projects', 'nav.projects', (p) => [h('a', { href: `/projects/${p.id}`, text: `${p.code} · ${name(p)}` }), statusBadge('PROJECT', p.status)]],
  ['contracts', 'fields.contract', (c) => [c.code, name(c, 'title'), refName(c.supplier)]],
];

export async function render(container, ctx) {
  const q = ctx.query.q || '';
  const body = h('div', { class: 'stack' }, loadingBox());
  container.append(h('div', { class: 'page-head' }, h('h1', { tabindex: '-1', text: `${t('common.search')}: “${q}”` })), body);
  try {
    const data = await api.get('/search', { q });
    const cards = GROUPS.filter(([key]) => data[key] && data[key].length).map(([key, label, cells]) =>
      card(`${t(label)} (${data[key].length})`, dataTable(cells(data[key][0]).map((_, i) => ({ key: String(i), label: '', render: (row) => cells(row)[i] })), data[key])));
    replace(body, cards.length ? cards : h('div', { class: 'empty', text: t('common.noResults') }));
  } catch (error) { replace(body, errorBox(error)); }
}
