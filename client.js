/**
 * API client. Routes everything through fetch with the correct auth header.
 *
 * The auth token is provided by `tokenGetter`, which is set during app init:
 *   - When Clerk is configured, tokenGetter = () => session.getToken()
 *   - In dev mode, tokenGetter = () => `dev-user-<id>` (a fake bearer token)
 */

const API_BASE = import.meta.env.VITE_API_BASE || '';

let tokenGetter = async () => null;

export function setTokenGetter(fn) {
  tokenGetter = fn;
}

export class ApiError extends Error {
  constructor(message, status, code, payload) {
    super(message);
    this.status = status;
    this.code = code;
    this.payload = payload;
  }
}

async function request(path, { method = 'GET', body, query, signal } = {}) {
  const token = await tokenGetter();
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let url = `${API_BASE}${path}`;
  if (query && Object.keys(query).length) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v != null && v !== '') params.set(k, v);
    }
    url += `?${params}`;
  }

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });

  if (res.status === 204) return null;

  const text = await res.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { /* not JSON */ }

  if (!res.ok) {
    const msg = (payload && payload.error) || res.statusText || 'Request failed';
    const code = (payload && payload.code) || 'HTTP_ERROR';
    throw new ApiError(msg, res.status, code, payload);
  }
  return payload;
}

export const api = {
  // health & auth
  health:        () => request('/api/health'),
  syncUser:      (data) => request('/api/auth/sync', { method: 'POST', body: data }),
  me:            () => request('/api/me'),
  updateMe:      (data) => request('/api/me', { method: 'PUT', body: data }),

  // modules
  listModules:   (query) => request('/api/modules', { query }),
  getModule:     (code) => request(`/api/modules/${code}`),

  // majors
  listMajors:    () => request('/api/majors'),
  getMajor:      (code) => request(`/api/majors/${code}`),

  // requirements
  requirements:  (major = 'CS') => request('/api/requirements', { query: { major } }),

  // plans
  listPlans:     () => request('/api/plans'),
  createPlan:    (name) => request('/api/plans', { method: 'POST', body: { name } }),
  getPlan:       (id) => request(`/api/plans/${id}`),
  updatePlan:    (id, data) => request(`/api/plans/${id}`, { method: 'PUT', body: data }),
  deletePlan:    (id) => request(`/api/plans/${id}`, { method: 'DELETE' }),

  // plan entries
  addEntry:      (planId, data) => request(`/api/plans/${planId}/entries`, { method: 'POST', body: data }),
  updateEntry:   (planId, entryId, data) => request(`/api/plans/${planId}/entries/${entryId}`, { method: 'PUT', body: data }),
  deleteEntry:   (planId, entryId) => request(`/api/plans/${planId}/entries/${entryId}`, { method: 'DELETE' }),

  // computed
  validate:      (planId) => request(`/api/plans/${planId}/validate`),
  gpa:           (planId) => request(`/api/plans/${planId}/gpa`),
  progress:      (planId) => request(`/api/plans/${planId}/progress`),
  readyModules:  (planId, semesterId) =>
                     request(`/api/plans/${planId}/ready-modules`, { query: { semester_id: semesterId } }),

  // GPA scenarios
  gpaTarget:     (planId, cap, remainingMcs) =>
                     request(`/api/plans/${planId}/gpa/target`, { query: { cap, remaining_mcs: remainingMcs } }),
  gpaSuAdvice:   (planId, budgetMcs = 32) =>
                     request(`/api/plans/${planId}/gpa/su-advice`, { query: { budget_mcs: budgetMcs } }),
  gpaScenario:   (planId, overrides) =>
                     request(`/api/plans/${planId}/gpa/scenario`, { method: 'POST', body: { overrides } }),

  // recommendations
  recommendUEs:  (planId) => request('/api/recommendations/ues', { query: { plan_id: planId } }),

  // study groups
  optIn:         (data) => request('/api/study-groups/optin', { method: 'POST', body: data }),
  updateOptIn:   (id, data) => request(`/api/study-groups/optin/${id}`, { method: 'PUT', body: data }),
  optOut:        (id) => request(`/api/study-groups/optin/${id}`, { method: 'DELETE' }),
  matches:       (query) => request('/api/study-groups/matches', { query }),
  myOptins:      () => request('/api/study-groups/my-optins'),

  // sharing
  sharePlan:     (planId, data) => request(`/api/plans/${planId}/share`, { method: 'POST', body: data }),
  listShares:    (planId) => request(`/api/plans/${planId}/shares`),
  revokeShare:   (planId, shareId) => request(`/api/plans/${planId}/shares/${shareId}`, { method: 'DELETE' }),
  sharedWithMe:  () => request('/api/shared-with-me'),

  // badges
  badges:        () => request('/api/badges'),
};
