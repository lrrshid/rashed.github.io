// Accessible dialog: labelled, focus trapped inside, Escape closes (subject to the caller's guard),
// focus returns to the element that opened it.
import { h, icon, rememberFocus, restoreFocus, uid } from '../lib/dom.js';
import { t } from '../labels.js';

// Every open modal, so navigation and sign-out can close them properly (running their onClose cleanup,
// which unregisters unsaved-change guards and key listeners).
const openModals = new Set();

export function closeAllModals({ variant } = {}) {
  for (const modal of [...openModals].reverse()) {
    if (!variant || modal.variant === variant) modal.close(true);
  }
}

const FOCUSABLE ='a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

// titleDir 'auto': the title is data (a file name, a defect's own title), so it takes its own direction.
export function openModal({ title, titleDir, body, footer, size = 'md', beforeClose, onClose, variant = 'dialog' }) {
  const opener = document.activeElement;
  const openerKey = rememberFocus(document.body, opener);
  const titleId = uid('modal-title');
  const closeButton = h('button', { type: 'button', class: 'btn btn-icon', 'aria-label': t('common.close') }, icon('close'));
  const dialog = h('div', {
    class: `modal modal-${size} modal-${variant}`,
    role: 'dialog',
    'aria-modal': 'true',
    'aria-labelledby': titleId,
  },
  h('div', { class: 'modal-header' }, h('h2', { id: titleId, class: 'modal-title', dir: titleDir, tabindex: '-1', text: title }), closeButton),
  h('div', { class: 'modal-body' }, body),
  footer ? h('div', { class: 'modal-footer' }, footer) : null);
  const backdrop = h('div', { class: `modal-backdrop modal-backdrop-${variant}` }, dialog);

  let closed = false;
  async function close(force = false) {
    if (closed) return true;
    if (!force && beforeClose && !(await beforeClose())) return false;
    closed = true;
    openModals.delete(handle);
    document.removeEventListener('keydown', onKey, true);
    backdrop.remove();
    document.body.classList.toggle('modal-open', document.querySelector('.modal-backdrop') !== null);
    if (onClose) onClose();
    // The opener may have been rebuilt while the dialog was open (a list reloaded after saving): focus its new copy.
    if (opener && document.contains(opener)) opener.focus();
    else restoreFocus(document.body, openerKey);
    return true;
  }

  function onKey(event) {
    if (!document.body.contains(backdrop)) return;
    const topmost = [...document.querySelectorAll('.modal-backdrop')].pop();
    if (topmost !== backdrop) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'Tab') {
      const items = [...dialog.querySelectorAll(FOCUSABLE)].filter((el) => el.offsetParent !== null);
      if (!items.length) { event.preventDefault(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      // Focus on something outside the tab order (e.g. the title, focused when the panel opens) counts as the
      // edge too, so Shift+Tab or Tab from there wraps inside the dialog instead of escaping to the page behind.
      const at = items.indexOf(document.activeElement);
      if (event.shiftKey && at <= 0) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (at === -1 || at === items.length - 1)) { event.preventDefault(); first.focus(); }
    }
  }

  closeButton.addEventListener('click', () => close());
  if (variant === 'dialog') {
    // Only a single click closes it: the second press of a double-click on the button that opened the dialog
    // lands on the new backdrop (event.detail 2) and must not close the dialog it just opened.
    backdrop.addEventListener('mousedown', (event) => { if (event.target === backdrop && event.detail <= 1) close(); });
  }
  document.addEventListener('keydown', onKey, true);
  document.body.append(backdrop);
  document.body.classList.add('modal-open');
  // First field that can really take focus (a hidden or disabled control would leave focus on the page behind).
  const firstField = [...dialog.querySelectorAll('.modal-body input, .modal-body select, .modal-body textarea')]
    .find((el) => !el.disabled && el.offsetParent !== null);
  (firstField || dialog.querySelector(`#${titleId}`)).focus();
  const handle = { close, dialog, variant, isClosed: () => closed };
  openModals.add(handle);
  return handle;
}

export function confirmDialog({ title, body, confirmLabel, danger = false, cancelLabel }) {
  return new Promise((resolve) => {
    let result = false;
    const confirmBtn = h('button', { type: 'button', class: `btn ${danger ? 'btn-danger' : 'btn-primary'}`, text: confirmLabel });
    const cancelBtn = h('button', { type: 'button', class: 'btn', text: cancelLabel || t('common.cancel') });
    const modal = openModal({
      title,
      size: 'sm',
      body: typeof body === 'string' ? h('p', { text: body }) : body,
      footer: [cancelBtn, confirmBtn],
      onClose: () => resolve(result),
    });
    confirmBtn.addEventListener('click', () => { result = true; modal.close(true); });
    cancelBtn.addEventListener('click', () => modal.close(true));
    cancelBtn.focus();
  });
}

export function confirmDiscard() {
  return confirmDialog({
    title: t('confirm.discardTitle'),
    body: t('confirm.discardBody'),
    confirmLabel: t('confirm.discard'),
    cancelLabel: t('confirm.keepEditing'),
    danger: true,
  });
}
