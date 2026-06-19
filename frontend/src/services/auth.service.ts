import { apiClient, ensureAccessToken, getJson, tokenStorage } from "@/services/client";
import type { AxiosRequestConfig } from "axios";
import type { AuthResponse, User } from "@/types/api";

const skipAuthRefreshConfig: AxiosRequestConfig & { skipAuthRefresh?: boolean } = { skipAuthRefresh: true };

export const authService = {
  async login(payload: { email: string; password: string }) {
    const { data } = await apiClient.post<AuthResponse>("/auth/login", payload);
    tokenStorage.set(data.access_token);
    return data;
  },
  async register(payload: { email: string; password: string; full_name: string }) {
    const { data } = await apiClient.post<AuthResponse>("/auth/register", payload);
    tokenStorage.set(data.access_token);
    return data;
  },
  async forgotPassword(payload: { email: string }) {
    const { data } = await apiClient.post<{ status: string; message: string }>("/auth/forgot-password", payload, skipAuthRefreshConfig);
    return data;
  },
  async resetPassword(payload: { token: string; password: string }) {
    const { data } = await apiClient.post<{ status: string; message: string }>("/auth/reset-password", payload, skipAuthRefreshConfig);
    return data;
  },
  async refresh() {
    const token = await ensureAccessToken();
    return Boolean(token);
  },
  me: () => getJson<User>("/auth/me"),
  async logout() {
    try {
      await apiClient.post("/auth/logout");
    } finally {
      tokenStorage.clear();
    }
  },
};
