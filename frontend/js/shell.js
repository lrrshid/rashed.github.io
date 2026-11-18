// The sidebar (every module of the system) and the top bar: global search, department filter, language switch,
// alerts bell, admin role preview and sign-out.
import { api } from './api.js';
import { h, icon, replace } from './lib/dom.js';
import { language, setLanguage } from './lib/i18n.js';
import { departmentsInScope, isAdmin, lookupList, setDepartment, setViewAs, state, user } from './lib/state.js';
import { name, t } from './labels.js';
import { mode, setMode } from './lib/theme.js';
import { paletteButton } from './components/palette.js';
import { navigate } from './router.js';

// [key, path, icon, children]
function navModel() {
  return [
    ['home', '/', 'home'],
    ['capabilities', null, 'layers', [
      ['allCapabilities', '/capabilities'],
      ...lookupList('categories').filter((c) => !c.archived).map((c) => [`cat:${c.code}`, `/capabilities/category/${c.code}`, null, null, `${c.code} · ${name(c)}`]),
      ['completion', '/completion'], ['gaps', '/gaps'], ['aiCapabilities', '/ai'], ['development', '/development'],
    ]],
    ['projects', null, 'briefcase', [
      ['allProjects', '/projects'], ['activeProjects', '/projects?view=active'], ['delayedProjects', '/projects?view=delayed'],
      ['timeline', '/timeline'], ['gantt', '/gantt'], ['milestones', '/milestones'], ['risks', '/risks'], ['issues', '/issues'],
    ]],
    ['testing', '/testing', 'flask'],
    ['maintenance', '/maintenance', 'wrench'],
    ['decision', '/decision', 'compass'],
    ['reports', '/reports', 'chart'],
    ['documents', '/documents', 'folder'],
    ['alerts', '/alerts', 'bell'],
    ['settings', '/settings', 'settings'],
  ];
}

function isCurrent(path) {
  if (!path) return false;
  const here = window.location.pathname + window.location.search;
  if (path.includes('?')) return here === path;
  return window.location.pathname === path && !window.location.search.includes('view=');
}

export function renderSidebar(alertCount = 0) {
  const sidebar = document.getElementById('sidebar');
  const nav = h('nav', { class: 'nav' });
  for (const [key, path, iconName, children] of navModel()) {
    if (key === 'settings' && !isAdmin() && !(user() && user().permissions.includes('view'))) continue;
    if (children) {
      const open = children.some(([, p]) => p && (window.location.pathname === p.split('?')[0] || window.location.pathname.startsWith(`${p.split('?')[0]}/`)));
      const details = h('details', { class: 'nav-group', open: open || undefined },
        h('summary', {}, icon(iconName), h('span', { text: t(`nav.${key}`) }), icon('chevron', 'icon chev')));
      details.append(h('div', { class: 'nav-sub' }, children.map(([k, p, , , label]) =>
        h('a', { class: 'nav-link', href: p, 'aria-current': isCurrent(p) ? 'page' : undefined, text: label || t(`nav.${k}`) }))));
      nav.append(details);
    } else {
      nav.append(h('a', { class: 'nav-link', href: path, 'aria-current': isCurrent(path) ? 'page' : undefined },
        icon(iconName), h('span', { text: t(`nav.${key}`) }),
        key === 'alerts' && alertCount ? h('span', { class: 'nav-count', text: String(alertCount) }) : null));
    }
  }
  replace(sidebar,
    h('div', { class: 'brand' },
      h('img', { class: 'brand-mark', src: '/assets/icons/ng-logo.png', alt: '' }),
      h('div', {}, h('div', { class: 'brand-name', text: t('app.name') }), h('div', { class: 'brand-sub', text: t('app.subtitle') }))),
    nav,
    h('div', { class: 'sidebar-foot', text: t('nav.footer') }));
}

export function renderTopbar() {
  const bar = document.getElementById('topbar');
  const search = h('input', { class: 'input', type: 'search', placeholder: t('top.search'), 'aria-label': t('common.search') });
  search.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && search.value.trim()) navigate(`/search?q=${encodeURIComponent(search.value.trim())}`);
  });
  const dept = h('select', { class: 'select', 'aria-label': t('fields.department') },
    h('option', { value: '', text: t('common.allDepartments') }),
    departmentsInScope().map((d) => h('option', { value: d.id, text: name(d), selected: state.department === d.id || undefined })));
  dept.addEventListener('change', () => { setDepartment(dept.value || null); navigate(window.location.pathname + window.location.search, { replace: true }); });

  const lang = h('div', { class: 'lang-switch', role: 'group', 'aria-label': t('top.language') },
    h('button', { type: 'button', lang: 'en', 'aria-pressed': language() === 'en' ? 'true' : 'false', text: 'EN', onclick: () => setLanguage('en') }),
    h('button', { type: 'button', lang: 'ar', 'aria-pressed': language() === 'ar' ? 'true' : 'false', text: 'ع', onclick: () => setLanguage('ar') }));

  const tools = h('div', { class: 'topbar-tools' }, dept, lang,
    h('a', { class: 'btn btn-icon bell', href: '/alerts', 'aria-label': t('top.alerts') }, icon('bell'), h('span', { class: 'badge-count', id: 'bell-count', hidden: true })));

  const real = state.session.user;
  if (real.permissions.includes('admin') || state.viewAs) {
    const select = h('select', { class: 'select', 'aria-label': t('top.viewAs') },
      h('option', { value: '', text: t('top.viewAsSelf') }),
      lookupList('roles').map((r) => h('option', { value: r.code, text: name(r), selected: state.viewAs === r.code || undefined })));
    select.addEventListener('change', () => { setViewAs(select.value || null); window.location.reload(); });
    tools.append(h('label', { class: 'view-as' }, h('span', { text: t('top.viewAs') }), select));
  }
  // The signed-in person: initials in a gold badge, then the name.
  const words = (real.displayName || '').trim().split(/\s+/).filter(Boolean);
  const initials = words.length ? `${words[0][0]}${words.length > 1 ? words[words.length - 1][0] : ''}`.toUpperCase() : '?';
  tools.append(h('span', { class: 'topbar-user' }, h('span', { class: 'topbar-avatar', 'aria-hidden': 'true', text: initials }),
    h('span', { text: real.displayName })),
    h('button', { type: 'button', class: 'btn btn-icon', 'aria-label': t('top.signOut'), title: t('top.signOut'), onclick: signOut }, icon('logout')));

  // At the start of the bar (top right in Arabic): light / dark mode and the colours for this browser (administrators
  // also reach the colours saved for everyone from the colours panel).
  const modeBtn = h('button', { type: 'button', class: 'btn btn-icon', 'aria-label': t('top.darkMode'), title: t('top.darkMode'),
    'aria-pressed': mode() === 'dark' ? 'true' : 'false' }, icon(mode() === 'dark' ? 'sun' : 'moon'));
  modeBtn.addEventListener('click', () => {
    const next = mode() === 'dark' ? 'light' : 'dark';
    setMode(next);
    modeBtn.setAttribute('aria-pressed', next === 'dark' ? 'true' : 'false');
    replace(modeBtn, icon(next === 'dark' ? 'sun' : 'moon'));
  });
  const quick = h('div', { class: 'topbar-quick' }, modeBtn, paletteButton({ buttonClass: 'btn btn-icon', forEveryone: isAdmin() }));

  replace(bar,
    h('button', { type: 'button', class: 'btn btn-icon menu-btn', 'aria-label': t('top.menu'), onclick: () => document.getElementById('app').classList.toggle('nav-open') }, icon('menu')),
    quick,
    h('div', { class: 'global-search' }, icon('search'), search),
    tools);
  const banner = document.querySelector('.preview-banner');
  if (banner) banner.remove();
  if (state.viewAs) {
    const role = lookupList('roles').find((r) => r.code === state.viewAs);
    bar.after(h('div', { class: 'preview-banner', role: 'status' },
      t('top.previewing', { role: role ? name(role) : state.viewAs }), ' ',
      h('button', { type: 'button', class: 'btn btn-sm', text: t('top.leavePreview'), onclick: () => { setViewAs(null); window.location.reload(); } })));
  }
}

async function signOut() {
  try { await api.del('/session'); } catch { /* signed out anyway */ }
  setViewAs(null);
  window.location.assign('/');
}

export function setAlertCount(n) {
  const el = document.getElementById('bell-count');
  if (!el) return;
  el.hidden = !n;
  el.textContent = n > 99 ? '99+' : String(n);
}
