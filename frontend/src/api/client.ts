// ============================================================
// DialEasypro — API Client
// Axios instance with JWT auth + automatic token refresh
// Base URL: /api/v1/ (proxied to Django backend in dev)
// ============================================================
import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

const BASE_URL = (typeof import.meta !== "undefined" ? (import.meta as { env?: { VITE_API_BASE_URL?: string } }).env?.VITE_API_BASE_URL : undefined) || 'https://api.dialeasypro.easyian.com/';

export const apiClient = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30_000,
});

// ---- Request interceptor: attach Bearer token and dynamic tenant URL ----
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const workspace = localStorage.getItem('tenant_workspace');
  if (workspace) {
    let baseUrl = BASE_URL || window.location.origin;
    if (baseUrl.includes('localhost')) {
      baseUrl = baseUrl.replace('localhost', `${workspace}.localhost`);
    } else {
      try {
        const urlObj = new URL(baseUrl);
        urlObj.hostname = `${workspace}.${urlObj.hostname.replace(/^www\./, '')}`;
        baseUrl = urlObj.origin;
      } catch (e) {}
    }
    config.baseURL = `${baseUrl}/api/v1`;

    // Always send the tenant schema as a header.
    // TenantSchemaFromTokenMiddleware on the backend uses this as a fallback
    // for requests that arrive before a JWT is available (e.g. the login call
    // and the token-refresh call), ensuring the DB is always on the right schema.
    config.headers['X-Tenant-Schema'] = workspace;
  }

  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// ---- Response interceptor: handle 401 + refresh ----
let isRefreshing = false;
let failedQueue: Array<{ resolve: (v: string) => void; reject: (e: unknown) => void }> = [];

const processQueue = (error: unknown, token: string | null) => {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          original.headers['Authorization'] = `Bearer ${token}`;
          return apiClient(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      const refresh = localStorage.getItem('refresh_token');
      if (!refresh) {
        isRefreshing = false;
        clearAuth();
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        const refreshUrl = `${original.baseURL || `${BASE_URL}/api/v1`}/auth/refresh/`;
        const { data } = await axios.post(refreshUrl, { refresh });
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);
        apiClient.defaults.headers['Authorization'] = `Bearer ${data.access}`;
        processQueue(null, data.access);
        original.headers['Authorization'] = `Bearer ${data.access}`;
        return apiClient(original);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearAuth();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export const clearAuth = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('agent');
};

export const setAuth = (access: string, refresh: string) => {
  localStorage.setItem('access_token', access);
  localStorage.setItem('refresh_token', refresh);
};

export default apiClient;
