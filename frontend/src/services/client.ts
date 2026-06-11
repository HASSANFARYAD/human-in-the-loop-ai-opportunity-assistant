import axios, { AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";

type ApiErrorDetail =
  | string
  | {
      message?: string;
      status?: string;
      source?: string;
    };

export type ApiError = Error & {
  detail?: ApiErrorDetail;
  apiStatus?: string;
  source?: string;
  httpStatus?: number;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean; skipAuthRefresh?: boolean };
type RefreshRequestConfig = AxiosRequestConfig & { skipAuthRefresh?: boolean };

let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

export const tokenStorage = {
  get: () => accessToken,
  set: (token: string) => {
    accessToken = token;
  },
  clear: () => {
    accessToken = null;
    if (typeof window !== "undefined") window.localStorage.removeItem("access_token");
  },
};

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}${API_PREFIX}`,
  timeout: 30000,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = apiClient
      .post<{ access_token: string }>("/auth/refresh", undefined, { skipAuthRefresh: true } as RefreshRequestConfig)
      .then((response) => {
        tokenStorage.set(response.data.access_token);
        return response.data.access_token;
      })
      .catch(() => {
        tokenStorage.clear();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function ensureAccessToken(): Promise<string | null> {
  return tokenStorage.get() ?? refreshAccessToken();
}

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: ApiErrorDetail }>) => {
    const originalRequest = error.config as RetriableRequestConfig | undefined;
    const shouldRefresh =
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !originalRequest.skipAuthRefresh &&
      !originalRequest.url?.includes("/auth/login") &&
      !originalRequest.url?.includes("/auth/register") &&
      !originalRequest.url?.includes("/auth/refresh");

    if (shouldRefresh) {
      originalRequest._retry = true;
      const token = await refreshAccessToken();
      if (token) {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return apiClient(originalRequest);
      }
    }

    if (error.response?.status === 401) {
      tokenStorage.clear();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.assign("/login");
      }
    }
    const detail = error.response?.data?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? error.message;
    const apiError = new Error(message) as ApiError;
    apiError.detail = detail;
    apiError.apiStatus = typeof detail === "string" ? undefined : detail?.status;
    apiError.source = typeof detail === "string" ? undefined : detail?.source;
    apiError.httpStatus = error.response?.status;
    return Promise.reject(apiError);
  },
);

export async function getJson<T>(url: string, params?: Record<string, unknown>) {
  const { data } = await apiClient.get<T>(url, { params });
  return data;
}
