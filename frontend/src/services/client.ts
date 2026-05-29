import axios, { AxiosError, InternalAxiosRequestConfig } from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_PREFIX = "/api/v1";

export const tokenStorage = {
  get: () => (typeof window === "undefined" ? null : window.localStorage.getItem("access_token")),
  set: (token: string) => {
    if (typeof window !== "undefined") window.localStorage.setItem("access_token", token);
  },
  clear: () => {
    if (typeof window !== "undefined") window.localStorage.removeItem("access_token");
  },
};

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}${API_PREFIX}`,
  timeout: 30000,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = tokenStorage.get();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<{ detail?: string }>) => {
    if (error.response?.status === 401) {
      tokenStorage.clear();
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        window.location.assign("/login");
      }
    }
    return Promise.reject(new Error(error.response?.data?.detail ?? error.message));
  },
);

export async function getJson<T>(url: string, params?: Record<string, unknown>) {
  const { data } = await apiClient.get<T>(url, { params });
  return data;
}
