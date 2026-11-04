// A date box that shows and takes dd/mm/yyyy, the same on every PC and in both languages (owner decision 26 Oct 2026:
// a native <input type=date> follows each browser's own region), with a calendar button that opens a month calendar.
//
// The contract callers rely on, the same as the native date input it replaces: the input's `.value` reads and writes
// an ISO date "YYYY-MM-DD" ('' when empty or not a date yet), `.min` / `.max` take ISO dates, and it fires `input`
// and `change` as the user types or picks a day. What the user sees is dd/mm/yyyy text. A half-typed date reads as
// '' like the native input's; `dateInvalid` (isBadDate) says so, so a form never sends it as "no date".
//
// The calendar is built here (no third-party picker: the CSP allows only this site's scripts) and shown in the top
// layer (the popover API), so a dialog's scrolling body or the Operations full screen never clips it. Escape closes
// only the calendar, never the dialog around it.
import { h } from '../lib/dom.js';
import { isolate, t } from '../labels.js';
import { glyph } from '../lib/svg.js';
import { isRtl, locale } from '../lib/i18n.js';
import { formatPlainDate, parseDateText, todayInZone } from '../lib/format.js';

const nativeValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');

// True when the box holds text that is not a date (half typed, 31/02/2026, a two-digit year).
export function isBadDate(control) {
  return Boolean(control && control.dateInvalid);
}

// ---- calendar dates as plain numbers (UTC, so they never shift by time zone)
function partsOf(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return { y, m, d };
}
function isoOf(y, m, d) {
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toISOString().slice(0, 10);
}
function addDays(iso, days) {
  const { y, m, d } = partsOf(iso);
  return isoOf(y, m, d + days);
}
// The same day in another month, or that month's last day (31 Jan + 1 month = 28 or 29 Feb).
function addMonths(iso, months) {
  const { y, m, d } = partsOf(iso);
  const last = new Date(Date.UTC(y, m - 1 + months + 1, 0)).getUTCDate();
  return isoOf(y, m + months, Math.min(d, last));
}
// The calendar's first column, as Date.getUTCDay counts (0 Sunday … 6 Saturday): Monday, the start of the UAE working
// week.
const WEEK_START = 1;
// A day's column in the calendar: 0 (the week's first day) … 6.
function weekday(iso) {
  const { y, m, d } = partsOf(iso);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() - WEEK_START + 7) % 7;
}
const utc = (iso) => { const { y, m, d } = partsOf(iso); return new Date(Date.UTC(y, m - 1, d)); };

let formats = null;
function intl() {
  if (!formats) {
    formats = {
      month: new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', month: 'long', year: 'numeric' }),
      // Arabic short weekday names are the whole word; the one-letter forms (ن ث ر…) fit the narrow columns.
      weekday: new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', weekday: isRtl() ? 'narrow' : 'short' }),
      weekdayLong: new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', weekday: 'long' }),
      full: new Intl.DateTimeFormat(locale(), { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
    };
  }
  return formats;
}

// Makes `input` an ISO-valued date box (see the contract above).
function upgrade(input) {
  const text = () => nativeValue.get.call(input);
  Object.defineProperties(input, {
    value: {
      configurable: true,
      get: () => parseDateText(text()) || '',
      set: (v) => {
        const iso = parseDateText(v);
        nativeValue.set.call(input, iso ? formatPlainDate(iso) : '');
      },
    },
    dateText: { configurable: true, get: text },
    dateInvalid: { configurable: true, get: () => text().trim() !== '' && !parseDateText(text()) },
  });
  // A typed date settles into dd/mm/yyyy (1-2-2026 → 01/02/2026, a pasted 2026-02-01 too).
  const normalise = () => {
    const iso = parseDateText(text());
    if (iso && text() !== formatPlainDate(iso)) nativeValue.set.call(input, formatPlainDate(iso));
  };
  input.addEventListener('change', normalise);
  input.addEventListener('blur', normalise);
}

// options: id, name, value (ISO), min, max (ISO), required, describedBy, label (the box's visible label: names its
// calendar button, "Choose date: Target date", so a form's several buttons can be told apart by a screen reader or
// voice control), className (the box's look: 'input' in forms, 'ops-date' on Operations), variant ('ops' for the dark
// Operations look of the button) and attrs (extra attributes for the box: data-focus-key…).
// Returns { node, input }: put `node` on the page, read and write `input`.
export function dateField({ id, name, value = '', min, max, required = false, describedBy, label, className = 'input', variant, attrs = {} }) {
  const input = h('input', {
    ...attrs,
    type: 'text',
    id,
    name,
    class: `${className} date-field-input`,
    dir: 'ltr',
    inputmode: 'numeric',
    autocomplete: 'off',
    spellcheck: 'false',
    placeholder: t('dateField.placeholder'),
    'aria-describedby': describedBy || undefined,
    required: required || undefined,
    'aria-required': required ? 'true' : undefined,
    min,
    max,
  });
  upgrade(input);
  input.value = value;

  const buttonName = label ? t('dateField.chooseFor', { field: isolate(label) }) : t('dateField.choose');
  const button = h('button', {
    type: 'button', class: 'date-field-btn', 'aria-label': buttonName, 'aria-haspopup': 'dialog', 'aria-expanded': 'false',
  }, glyph('calendar'));
  const node = h('div', { class: variant ? `date-field date-field-${variant}` : 'date-field' }, input, button);
  const calendar = createCalendar({ node, input, button, name: buttonName });

  button.addEventListener('click', () => (calendar.isOpen() ? calendar.close({ focus: input }) : calendar.open()));
  input.addEventListener('keydown', (event) => {
    if (event.altKey && event.key === 'ArrowDown') {
      event.preventDefault();
      calendar.open();
    }
  });
  return { node, input };
}

function createCalendar({ node, input, button, name }) {
  const title = h('p', { class: 'date-pop-title', 'aria-live': 'polite' });
  const prev = h('button', { type: 'button', class: 'date-pop-nav', 'aria-label': t('dateField.previousMonth') }, glyph('chevronStart'));
  const next = h('button', { type: 'button', class: 'date-pop-nav', 'aria-label': t('dateField.nextMonth') }, glyph('chevronEnd'));
  const body = h('tbody');
  const pop = h('div', { class: 'date-pop', role: 'dialog', 'aria-label': name, hidden: true },
    h('div', { class: 'date-pop-head' }, prev, title, next),
    h('table', { class: 'date-pop-grid', role: 'grid' },
      h('thead', {}, h('tr', {}, [0, 1, 2, 3, 4, 5, 6].map((i) => {
        const day = new Date(Date.UTC(2023, 11, 31 + WEEK_START + i));  // 31 Dec 2023 was a Sunday
        return h('th', { scope: 'col', abbr: intl().weekdayLong.format(day), text: intl().weekday.format(day) });
      }))),
      body));
  const usePopover = typeof pop.showPopover === 'function';
  if (usePopover) pop.setAttribute('popover', 'manual');

  let open = false;
  let view = '';    // any day of the month shown
  let active = '';  // the day keyboard focus is on

  const minOf = () => parseDateText(input.getAttribute('min')) || '';
  const maxOf = () => parseDateText(input.getAttribute('max')) || '';
  const outOfRange = (iso) => Boolean((minOf() && iso < minOf()) || (maxOf() && iso > maxOf()));

  function render() {
    const { y, m } = partsOf(view);
    const first = isoOf(y, m, 1);
    const start = addDays(first, -weekday(first));
    const today = todayInZone();
    const chosen = input.value;
    title.textContent = intl().month.format(utc(first));
    // The arrows stop at the months that hold no day in range.
    prev.disabled = Boolean(minOf() && isoOf(y, m, 0) < minOf());
    next.disabled = Boolean(maxOf() && isoOf(y, m + 1, 1) > maxOf());
    const rows = [];
    for (let week = 0; week < 6; week += 1) {
      rows.push(h('tr', {}, [0, 1, 2, 3, 4, 5, 6].map((i) => {
        const iso = addDays(start, week * 7 + i);
        const disabled = outOfRange(iso);
        const classes = ['date-pop-day',
          partsOf(iso).m !== m ? 'is-outside' : '', iso === today ? 'is-today' : '', iso === chosen ? 'is-selected' : ''];
        return h('td', { role: 'gridcell', 'aria-selected': iso === chosen ? 'true' : 'false' },
          h('button', {
            type: 'button',
            class: classes.filter(Boolean).join(' '),
            tabindex: iso === active ? '0' : '-1',
            'data-date': iso,
            'aria-label': intl().full.format(utc(iso)),
            'aria-current': iso === today ? 'date' : undefined,
            'aria-disabled': disabled ? 'true' : undefined,
            text: String(partsOf(iso).d),
          }));
      })));
    }
    body.replaceChildren(...rows);
  }

  const dayButton = (iso) => body.querySelector(`[data-date="${iso}"]`);

  function moveTo(iso, { focus = true } = {}) {
    active = iso;
    if (iso.slice(0, 7) !== view.slice(0, 7)) view = iso;
    render();
    if (focus) dayButton(active)?.focus();
  }

  function choose(iso) {
    if (outOfRange(iso)) return;
    input.value = iso;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
    close({ focus: input });
  }

  // Below the box, lined up with its start edge; above it when there is no room below; always on screen.
  function place() {
    const box = node.getBoundingClientRect();
    const width = pop.offsetWidth;
    const height = pop.offsetHeight;
    const viewWidth = document.documentElement.clientWidth;
    const left = Math.max(8, Math.min(isRtl() ? box.right - width : box.left, viewWidth - width - 8));
    const below = box.bottom + 4;
    const top = below + height > window.innerHeight - 8 && box.top - height - 4 >= 8 ? box.top - height - 4 : below;
    pop.style.left = `${Math.round(left)}px`;
    pop.style.top = `${Math.round(top)}px`;
  }

  // Keys while the calendar is open. Listening on window in the capture phase runs before the dialog's own Escape
  // and Tab handling (components/modal.js listens on document), so Escape closes the calendar only.
  function onKey(event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close({ focus: pop.contains(document.activeElement) ? input : null });
      return;
    }
    if (!pop.contains(event.target)) return;
    if (event.key === 'Tab') {
      // Leaving the calendar: it closes and focus goes back to its button, the next stop after the box.
      event.preventDefault();
      event.stopPropagation();
      close({ focus: button });
      return;
    }
    const onDay = event.target.matches('.date-pop-day');
    const side = isRtl() ? -1 : 1;  // the grid runs right to left in Arabic, so the arrows follow what the eye sees
    let target = null;
    if (event.key === 'PageUp') target = addMonths(active, event.shiftKey ? -12 : -1);
    else if (event.key === 'PageDown') target = addMonths(active, event.shiftKey ? 12 : 1);
    else if (onDay && event.key === 'ArrowLeft') target = addDays(active, -side);
    else if (onDay && event.key === 'ArrowRight') target = addDays(active, side);
    else if (onDay && event.key === 'ArrowUp') target = addDays(active, -7);
    else if (onDay && event.key === 'ArrowDown') target = addDays(active, 7);
    else if (onDay && event.key === 'Home') target = addDays(active, -weekday(active));
    else if (onDay && event.key === 'End') target = addDays(active, 6 - weekday(active));
    else if (onDay && (event.key === 'Enter' || event.key === ' ')) {
      event.preventDefault();
      event.stopPropagation();
      choose(active);
      return;
    }
    if (!target) return;
    event.preventDefault();
    event.stopPropagation();
    moveTo(target);
  }

  function onPointerDown(event) {
    if (!node.contains(event.target)) close({ focus: null });
  }
  const onScroll = () => place();
  const onFullScreen = () => close({ focus: null });

  body.addEventListener('click', (event) => {
    const day = event.target.closest('.date-pop-day');
    if (day && day.getAttribute('aria-disabled') !== 'true') choose(day.dataset.date);
  });
  // The arrow buttons keep focus, unless the month they lead to is the last one in range (they are then disabled).
  const turn = (months, arrow) => {
    moveTo(addMonths(active, months), { focus: false });
    if (arrow.disabled) dayButton(active)?.focus();
  };
  prev.addEventListener('click', () => turn(-1, prev));
  next.addEventListener('click', () => turn(1, next));
  // The page was left (or the dialog closed) with the calendar open: drop the window listeners with it. Taking the
  // calendar out of the document hides it even when it is put straight back (the Operations refresh moves the period
  // boxes into the rebuilt section): the browser hides it without a toggle event, so that is checked here too, or the
  // calendar would stay open for this code (the listeners, aria-expanded) with nothing on screen.
  const detached = new MutationObserver(() => {
    if (!node.isConnected || (usePopover && !pop.matches(':popover-open'))) close();
  });
  if (usePopover) pop.addEventListener('toggle', (event) => { if (event.newState === 'closed') close(); });

  function openCalendar() {
    if (open) return;
    open = true;
    const today = todayInZone();
    let start = input.value || today;
    if (minOf() && start < minOf()) start = minOf();
    if (maxOf() && start > maxOf()) start = maxOf();
    active = start;
    view = start;
    if (!pop.isConnected) node.append(pop);
    render();
    pop.hidden = false;
    if (usePopover) pop.showPopover();
    place();
    button.setAttribute('aria-expanded', 'true');
    node.classList.add('is-open');
    window.addEventListener('keydown', onKey, true);
    document.addEventListener('pointerdown', onPointerDown, true);
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);
    document.addEventListener('fullscreenchange', onFullScreen);
    detached.observe(document.body, { childList: true, subtree: true });
    dayButton(active)?.focus();
  }

  function close({ focus = null } = {}) {
    if (!open) return;
    open = false;
    window.removeEventListener('keydown', onKey, true);
    document.removeEventListener('pointerdown', onPointerDown, true);
    window.removeEventListener('scroll', onScroll, true);
    window.removeEventListener('resize', onScroll);
    document.removeEventListener('fullscreenchange', onFullScreen);
    detached.disconnect();
    if (usePopover && pop.matches(':popover-open')) pop.hidePopover();
    pop.hidden = true;
    button.setAttribute('aria-expanded', 'false');
    node.classList.remove('is-open');
    if (focus) focus.focus();
  }

  return { open: openCalendar, close, isOpen: () => open };
}
