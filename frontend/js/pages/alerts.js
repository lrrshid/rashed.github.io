// Alert centre: automatic alerts for the user's role and departments, filterable by type and severity, acknowledged
// per user.
import { api } from '../api.js';
import { h, replace } from '../lib/dom.js';
import { name, t } from '../labels.js';
import { formatCount, formatDate } from '../lib/format.js';
import { errorBox, field, kpiTile, loadingBox, selectEl, toast } from '../components/ui.js';
import { refreshAlertCount } from '../main.js';

const SEVERITY_COLORS = { CRITICAL: 'red', HIGH: 'orange', MEDIUM: 'amber', INFO: 'blue' };

export async function render(container, ctx) {
  let showAcked = ctx.query.acked === 'true';
  let type = ctx.query.type || '';
  let severity = ctx.query.severity || '';
  const body = h('div');
  container.append(h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: t('alerts.title') }),
    h('div', { class: 'page-sub', text: t('alerts.subtitle') }))), body);

  async function load() {
    replace(body, loadingBox());
    let d;
    try { d = await api.get('/alerts', { open: showAcked ? undefined : true }); } catch (e) { replace(body, errorBox(e, load)); return; }
    const items = d.items.filter((a) => (!type || a.type === type) && (!severity || a.severity === severity));
    const ack = async (keys) => {
      try { await api.post('/alerts/acknowledge', { keys }); toast(t('common.saved')); refreshAlertCount(); load(); } catch (e) { toast(e.message, true); }
    };
    const typeSel = selectEl([...new Set(d.items.map((a) => a.type))].map((k) => ({ value: k, label: t(`alerts.types.${k}`) })), type, { includeEmpty: true });
    typeSel.addEventListener('change', () => { type = typeSel.value; ctx.setQuery({ type, severity, acked: showAcked || undefined }); load(); });
    replace(body,
      h('div', { class: 'kpis' }, ['CRITICAL', 'HIGH', 'MEDIUM', 'INFO'].map((s) => kpiTile({ label: t(`alerts.severity.${s}`), value: formatCount(d.counts[s]),
        tone: s === 'CRITICAL' && d.counts[s] ? 'red' : s === 'HIGH' && d.counts[s] ? 'amber' : undefined,
        onClick: () => { severity = severity === s ? '' : s; ctx.setQuery({ type, severity, acked: showAcked || undefined }); load(); } }))),
      h('div', { class: 'toolbar', style: 'margin-top:12px' },
        h('div', { class: 'filters', style: 'margin:0' }, field(t('documents.fields.type'), typeSel),
          h('label', { class: 'checks' }, h('input', { type: 'checkbox', checked: showAcked || undefined, onchange: (e) => { showAcked = e.target.checked; ctx.setQuery({ type, severity, acked: showAcked || undefined }); load(); } }), t('alerts.showAcknowledged'))),
        items.some((a) => !a.acknowledged) ? h('button', { type: 'button', class: 'btn', text: t('alerts.acknowledgeAll'), onclick: () => ack(items.filter((a) => !a.acknowledged).map((a) => a.key)) }) : null),
      items.length ? h('div', { class: 'card' }, h('ul', { class: 'attention' }, items.map((a) => h('li', { class: a.severity === 'CRITICAL' || a.severity === 'HIGH' ? '' : 'amber', style: a.acknowledged ? 'opacity:.6' : '' },
        h('div', { class: 'card-head', style: 'margin:0' },
          h('span', { class: 'actions' }, h('span', { class: `badge c-${SEVERITY_COLORS[a.severity]}`, text: t(`alerts.severity.${a.severity}`) }),
            h('span', { class: 'small muted', text: t(`alerts.types.${a.type}`) }), a.date ? h('span', { class: 'small muted', text: formatDate(a.date) }) : null),
          a.acknowledged ? h('span', { class: 'small muted', text: t('alerts.acknowledged') })
            : h('button', { type: 'button', class: 'btn btn-sm', text: t('alerts.acknowledge'), onclick: () => ack([a.key]) })),
        h('a', { href: a.link, text: name(a, 'text') }))))) : h('div', { class: 'empty', text: t('common.noResults') }));
  }
  await load();
}
