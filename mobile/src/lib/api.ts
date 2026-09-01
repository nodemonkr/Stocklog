import * as SecureStore from 'expo-secure-store';

const PRIMARY_ORIGIN = String(process.env.EXPO_PUBLIC_API_URL || 'http://somensomes.iptime.org:8100').replace(/\/+$/, '');
const FALLBACK_ORIGIN = String(process.env.EXPO_PUBLIC_API_FALLBACK_URL || 'http://somensomes.iptime.org:3000').replace(/\/+$/, '');
const TOKEN_KEY = 'stocklog_access_token_v1';

let activeOrigin = PRIMARY_ORIGIN;
let lastProbeAt = 0;

export class ApiError extends Error {
  status: number;
  data: any;
  constructor(message: string, status = 0, data: any = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}


const adminDiagnosticSeen = new Map<string, number>();
function reportAdminDiagnostic(origin: string, token: string | null, path: string, method: string, requestId: string, error: ApiError) {
  if (!token || !path.includes('/api/admin/') || path.includes('/api/admin/sync-error-logs') || error.status === 401) return;
  if (!/(sync|market-data|theme|classification)/i.test(path)) return;
  const signature = `${method}|${path}|${error.status}|${String(error.message||'').slice(0,120)}`;
  const now = Date.now(), last = adminDiagnosticSeen.get(signature) || 0;
  if (now - last < 60_000) return;
  adminDiagnosticSeen.set(signature, now);
  const payload = { event:'ADMIN_SYNC_API_ERROR', message:String(error.message||'').slice(0,12000), stack:String(error.stack||'').slice(0,30000), url:path.slice(0,4000), method:method.toUpperCase().slice(0,20), status:error.status||null, request_id:requestId.slice(0,120), context:{ source:'mobile', response:error.data } };
  void fetch(`${origin}/api/admin/sync-error-logs/client-event`, { method:'POST', headers:{ Authorization:`Bearer ${token}`, 'Content-Type':'application/json', Accept:'application/json' }, body:JSON.stringify(payload) }).catch(()=>{});
}

export async function getToken() {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function setToken(token: string) {
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

async function probe(origin: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 2500);
  try {
    const r = await fetch(`${origin}/health?_mobile=${Date.now()}`, { signal: controller.signal });
    return r.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function resolveApiOrigin(force = false) {
  if (!force && Date.now() - lastProbeAt < 60_000) return activeOrigin;
  lastProbeAt = Date.now();
  if (await probe(PRIMARY_ORIGIN)) {
    activeOrigin = PRIMARY_ORIGIN;
    return activeOrigin;
  }
  if (FALLBACK_ORIGIN && FALLBACK_ORIGIN !== PRIMARY_ORIGIN && await probe(FALLBACK_ORIGIN)) {
    activeOrigin = FALLBACK_ORIGIN;
    return activeOrigin;
  }
  activeOrigin = PRIMARY_ORIGIN;
  return activeOrigin;
}

export function currentApiOrigin() {
  return activeOrigin;
}

export function websocketUrl(path: string, token?: string | null) {
  const base = activeOrigin.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
  const clean = path.startsWith('/') ? path : `/${path}`;
  const join = clean.includes('?') ? '&' : '?';
  return `${base}${clean}${token ? `${join}token=${encodeURIComponent(token)}` : ''}`;
}

function queryString(params?: Record<string, unknown>) {
  if (!params) return '';
  const pairs: string[] = [];
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    if (Array.isArray(value)) {
      value.forEach(v => pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(v))}`));
    } else {
      pairs.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
    }
  });
  return pairs.length ? `?${pairs.join('&')}` : '';
}

async function parseResponse(r: Response) {
  const text = await r.text();
  let data: any = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!r.ok) {
    const message = typeof data === 'object' && data?.detail
      ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
      : typeof data === 'string' && data
        ? data
        : `HTTP ${r.status}`;
    throw new ApiError(message, r.status, data);
  }
  return data;
}

export async function apiRequest<T = any>(
  path: string,
  options: RequestInit & { params?: Record<string, unknown>; auth?: boolean; timeout?: number } = {},
): Promise<T> {
  const { params, auth = true, timeout = 30_000, ...fetchOptions } = options;
  const origin = await resolveApiOrigin();
  const token = auth ? await getToken() : null;
  const requestId = `mobile-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const headers: Record<string, string> = {
    Accept: 'application/json',
    'X-Request-ID': requestId,
    ...(fetchOptions.headers as Record<string, string> || {}),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (fetchOptions.body && typeof fetchOptions.body === 'string' && !headers['Content-Type']) headers['Content-Type'] = 'application/json';

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const url = `${origin}${path}${queryString(params)}`;
  try {
    const r = await fetch(url, { ...fetchOptions, headers, signal: controller.signal });
    return await parseResponse(r) as T;
  } catch (error: any) {
    if (error instanceof ApiError) {
      reportAdminDiagnostic(origin, token, path, String(fetchOptions.method || 'GET'), requestId, error);
      throw error;
    }
    // One transparent network retry through the fallback gateway.
    if (origin === PRIMARY_ORIGIN && FALLBACK_ORIGIN && FALLBACK_ORIGIN !== PRIMARY_ORIGIN) {
      const reachable = await probe(FALLBACK_ORIGIN);
      if (reachable) {
        activeOrigin = FALLBACK_ORIGIN;
        lastProbeAt = Date.now();
        const fallbackUrl = `${FALLBACK_ORIGIN}${path}${queryString(params)}`;
        const fallbackController = new AbortController();
        const fallbackTimer = setTimeout(() => fallbackController.abort(), timeout);
        try {
          const r = await fetch(fallbackUrl, { ...fetchOptions, headers, signal: fallbackController.signal });
          return await parseResponse(r) as T;
        } catch (fallbackError: any) {
          if (fallbackError instanceof ApiError) throw fallbackError;
          throw new ApiError(fallbackError?.name === 'AbortError' ? '보조 서버 응답 시간도 초과되었습니다.' : 'StockLog 보조 서버에 연결하지 못했습니다.');
        } finally {
          clearTimeout(fallbackTimer);
        }
      }
    }
    throw new ApiError(error?.name === 'AbortError' ? '서버 응답 시간이 초과되었습니다.' : 'StockLog 서버에 연결하지 못했습니다.');
  } finally {
    clearTimeout(timer);
  }
}

export const get = <T = any>(path: string, params?: Record<string, unknown>, auth = true) => apiRequest<T>(path, { method: 'GET', params, auth });
export const post = <T = any>(path: string, body?: unknown, auth = true) => apiRequest<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body), auth });
export const postParams = <T = any>(path: string, body?: unknown, params?: Record<string, unknown>, auth = true) => apiRequest<T>(path, { method: 'POST', params, body: body === undefined ? undefined : JSON.stringify(body), auth });
export const put = <T = any>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PUT', body: JSON.stringify(body ?? {}) });
export const patch = <T = any>(path: string, body?: unknown) => apiRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) });
export const del = <T = any>(path: string, params?: Record<string, unknown>) => apiRequest<T>(path, { method: 'DELETE', params });
