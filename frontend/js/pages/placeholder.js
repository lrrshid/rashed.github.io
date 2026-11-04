// Modules of later build phases: the navigation is complete from day one; these pages say what is coming.
import { h } from '../lib/dom.js';
import { t } from '../labels.js';

export function render(container, { meta }) {
  const title = t(meta.titleKey || 'app.name');
  container.append(
    h('div', { class: 'page-head' }, h('div', {}, h('h1', { tabindex: '-1', text: title }))),
    h('div', { class: 'card' }, h('p', { text: t('placeholder.body') })));
}
