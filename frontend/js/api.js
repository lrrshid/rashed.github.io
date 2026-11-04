// The only module that calls fetch(). Adds the CSRF header, parses the uniform error format,
// supports cancelling stale requests (AbortController) and reports expired sessions.
import { serverText, t } from './labels.js';
import { state } from './lib/state.js';

const BASE = '/api/v1';
let csrfToken = null;
let onUnauthenticated = () => {};

export function setCsrfToken(token) {
  csrfToken = token || null;
}

export function setUnauthenticatedHandler(handler) {
  onUnauthenticated = handler;
}

// The server writes its messages in English; serverText() shows them in Arabic when Arabic is chosen.
export class ApiError extends Error {
  constructor(status, body) {
    const code = (body && body.code) || 'ERROR';
    super(serverText(code, body && body.message) || t('errors.generic'));
    this.status = status;
    this.code = code;
    this.fieldErrors = ((body && body.fieldErrors) || []).map((fe) => ({ ...fe, message: serverText('FIELD', fe.message) }));
    this.requestId = body && body.requestId;
  }

  get isConflict() { return this.status === 409; }
  get isStale() { return this.code === 'STALE_VERSION'; }
  get isNotFound() { return this.status === 404; }
}

export function isAbort(error) {
  return error && error.name === 'AbortError';
}

function queryString(query) {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '' || value === false) continue;
    params.set(key, Array.isArray(value) ? value.join(',') : String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : '';
}

// form: a FormData (file uploads); the browser sets its multipart Content-Type and boundary itself.
export async function request(method, path, { body, form, query, signal } = {}) {
  const headers = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken;
  // Admin role preview: reads only (the server refuses a change made in a preview).
  if (method === 'GET' && state.viewAs) headers['X-View-As'] = state.viewAs;

  let response;
  try {
    response = await fetch(BASE + path + queryString(query), {
      method,
      headers,
      body: form || (body === undefined ? undefined : JSON.stringify(body)),
      credentials: 'same-origin',
      signal,
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(0, { code: 'NETWORK', message: t('errors.network') });
  }

  if (response.status === 204) return null;
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    const error = new ApiError(response.status, data || {});
    if (response.status === 401 && path !== '/session') onUnauthenticated(error);
    throw error;
  }
  return data;
}

export const api = {
  get: (path, query, signal) => request('GET', path, { query, signal }),
  post: (path, body, query) => request('POST', path, { body: body ?? {}, query }),
  put: (path, body, query) => request('PUT', path, { body, query }),
  patch: (path, body, query) => request('PATCH', path, { body, query }),
  del: (path, body, query) => request('DELETE', path, { body, query }),
  upload: (path, file, query) => {
    const form = new FormData();
    form.append('file', file, file.name);
    return request('POST', path, { form, query });
  },
};

// A file the server builds (CSV, Excel, PowerPoint): fetched with the session like any read, then handed to the
// browser as a download. Errors arrive as the usual JSON and are thrown as ApiError.
export async function download(path, query) {
  let response;
  try {
    const headers = state.viewAs ? { 'X-View-As': state.viewAs } : {};
    response = await fetch(BASE + path + queryString(query), { credentials: 'same-origin', headers });
  } catch {
    throw new ApiError(0, { code: 'NETWORK', message: t('errors.network') });
  }
  if (!response.ok) {
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    const error = new ApiError(response.status, data || {});
    if (response.status === 401) onUnauthenticated(error);
    throw error;
  }
  const match = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') || '');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = match ? match[1] : 'download';
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Fetch every page of a list endpoint (the server caps size at 100).
export async function getAll(path, query = {}, signal) {
  const items = [];
  let page = 0;
  for (;;) {
    const data = await api.get(path, { ...query, page, size: 100 }, signal);
    items.push(...data.items);
    page += 1;
    if (page >= data.totalPages) return { items, totalItems: data.totalItems };
  }
}
