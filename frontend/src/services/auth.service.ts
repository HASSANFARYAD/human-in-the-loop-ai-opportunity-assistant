import { apiClient, getJson, tokenStorage } from "@/services/client";
import type { AuthResponse, User } from "@/types/api";

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
  me: () => getJson<User>("/auth/me"),
  logout() {
    tokenStorage.clear();
  },
};
