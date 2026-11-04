// Session, lookups and the shell's global choices (department filter, role preview). Permission checks in the
// browser only decide what to show; the server enforces every rule again.
const listeners = new Set();

export const state = {
  session: null,          // GET /session
  lookups: null,          // GET /lookups
  department: null,       // global department filter (id string) or null for all
  viewAs: null,           // admin preview role code, or null
};

const VIEW_AS_KEY = 'cpc.viewAs';
const DEPT_KEY = 'cpc.department';
try {
  state.viewAs = window.sessionStorage.getItem(VIEW_AS_KEY) || null;
  state.department = window.sessionStorage.getItem(DEPT_KEY) || null;
} catch { /* storage unavailable */ }

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
function notify() { for (const fn of listeners) fn(state); }

export function setSession(session) {
  state.session = session;
  notify();
}
export function setLookups(lookups) { state.lookups = lookups; }

export function setDepartment(id) {
  state.department = id || null;
  try {
    if (id) window.sessionStorage.setItem(DEPT_KEY, id); else window.sessionStorage.removeItem(DEPT_KEY);
  } catch { /* ignore */ }
  notify();
}

export function setViewAs(code) {
  state.viewAs = code || null;
  try {
    if (code) window.sessionStorage.setItem(VIEW_AS_KEY, code); else window.sessionStorage.removeItem(VIEW_AS_KEY);
  } catch { /* ignore */ }
}

export function user() { return state.session ? state.session.user : null; }
export function can(permission) {
  const u = user();
  return Boolean(u && u.permissions.includes(permission));
}
// The real role may administer (the preview never may).
export function isAdmin() { return can('admin') && !state.viewAs; }
export function canEdit(permission) { return can(permission) && !state.viewAs; }

export function lookupList(name) { return (state.lookups && state.lookups[name]) || []; }
export function findById(list, id) { return lookupList(list).find((e) => e.id === String(id)) || null; }
export function statusDef(domain, code) {
  const list = (state.lookups && state.lookups.statuses[domain]) || [];
  return list.find((s) => s.code === code) || null;
}
export function statuses(domain) { return (state.lookups && state.lookups.statuses[domain]) || []; }
export function departmentsInScope() {
  const ids = user() && user().departmentIds;
  return lookupList('departments').filter((d) => !d.archived && (!ids || ids.includes(d.id)));
}
