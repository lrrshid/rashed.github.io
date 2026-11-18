// Boot: language, session, lookups, shell, routes.
import { api, setCsrfToken, setUnauthenticatedHandler } from './api.js';
import { h, replace } from './lib/dom.js';
import { applyDocumentLanguage } from './lib/i18n.js';
import { applyTheme, effectiveTheme, rememberTheme } from './lib/theme.js';
import { setTimeZone } from './lib/format.js';
import { setLookups, setSession, setViewAs, state } from './lib/state.js';
import { loadLanguage, t } from './labels.js';
import { renderLogin } from './pages/login.js';
import { route, setNavigateHandler, startRouter } from './router.js';
import { renderSidebar, renderTopbar, setAlertCount } from './shell.js';

route('/', () => import('./pages/dashboard.js'), { nav: 'home' });
route('/analytics', () => import('./pages/dashboard.js'), { nav: 'home', analytics: true });
route('/capabilities', () => import('./pages/registry.js'));
route('/capabilities/category/:code', () => import('./pages/registry.js'), { category: true });
route('/assets/:id', () => import('./pages/asset.js'));
route('/models/:id', () => import('./pages/model.js'));
route('/requirements/:id', () => import('./pages/requirement.js'));
route('/completion', () => import('./pages/completion.js'));
route('/gaps', () => import('./pages/gaps.js'));
route('/search', () => import('./pages/search.js'));
route('/projects', () => import('./pages/projects.js'));
route('/projects/:id', () => import('./pages/project.js'));
route('/timeline', () => import('./pages/timeline.js'));
route('/gantt', () => import('./pages/timeline.js'));
route('/milestones', () => import('./pages/milestones.js'));
route('/risks', () => import('./pages/risks.js'));
route('/issues', () => import('./pages/issues.js'));
for (const path of ['/testing', '/maintenance', '/ai', '/development', '/decision']) route(path, () => import('./pages/operations.js'));
route('/documents', () => import('./pages/documents.js'));
route('/alerts', () => import('./pages/alerts.js'));
route('/settings', () => import('./pages/settings.js'));
route('/audit', () => import('./pages/settings.js'));
route('/reports', () => import('./pages/reports.js'));

export function registerRoute(path, loader, meta) { route(path, loader, meta); }

async function boot() {
  applyDocumentLanguage();
  // Interface colours (Settings > Appearance), public so the sign-in page has them too; defaults if unreachable.
  const [theme] = await Promise.all([api.get('/appearance').then((d) => d.theme, () => null), loadLanguage()]);
  rememberTheme(theme);
  applyTheme(effectiveTheme());   // this device's own palette, if one was chosen
  document.title = t('app.name');
  const app = document.getElementById('app');
  setUnauthenticatedHandler(() => window.location.assign('/'));
  let session = null;
  try {
    session = await api.get('/session');
  } catch (error) {
    if (error.status === 401) {
      setViewAs(null);
      const options = await api.get('/session/options');
      app.classList.add('signed-out');
      renderLogin(document.getElementById('main'), options, () => window.location.reload());
      return;
    }
    replace(document.getElementById('main'), h('div', { class: 'error-box', text: error.message }));
    return;
  }
  if (state.viewAs && !session.viewAs) setViewAs(null);  // preview no longer allowed (role changed)
  setCsrfToken(session.csrfToken);
  setTimeZone(session.timezone);
  setSession(session);
  setLookups(await api.get('/lookups'));
  renderTopbar();
  setNavigateHandler(() => { renderSidebar(); document.getElementById('app').classList.remove('nav-open'); });
  startRouter();
  refreshAlertCount();
}

export async function refreshAlertCount() {
  try {
    const data = await api.get('/alerts/count');
    setAlertCount(data.open);
    renderSidebar(data.open);
  } catch { /* the alert centre arrives in a later phase */ }
}

boot();
