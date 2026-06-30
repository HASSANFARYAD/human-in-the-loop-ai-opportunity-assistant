import { describe, it, expect, vi, beforeEach } from "vitest";
import type { AuthResponse } from "@/types/api";

vi.mock("@/services/client", () => ({
  apiClient: {
    post: vi.fn(),
  },
  tokenStorage: {
    get: vi.fn(),
    set: vi.fn(),
    clear: vi.fn(),
  },
  refreshSession: vi.fn(),
}));

import { authService } from "@/services/auth.service";
import { apiClient, tokenStorage, refreshSession } from "@/services/client";

const mockAuthResponse: AuthResponse = {
  access_token: "test-token",
  token_type: "bearer",
  user: { id: 1, email: "test@example.com", full_name: "Test User" },
};

describe("authService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("login", () => {
    it("posts to /auth/login and stores the token", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockAuthResponse });

      const result = await authService.login({ email: "test@example.com", password: "password123" });

      expect(apiClient.post).toHaveBeenCalledWith("/auth/login", {
        email: "test@example.com",
        password: "password123",
      });
      expect(tokenStorage.set).toHaveBeenCalledWith("test-token");
      expect(result).toEqual(mockAuthResponse);
    });
  });

  describe("register", () => {
    it("posts to /auth/register and stores the token", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockAuthResponse });

      const result = await authService.register({
        email: "test@example.com",
        password: "StrongPass1!",
        full_name: "Test User",
      });

      expect(apiClient.post).toHaveBeenCalledWith("/auth/register", {
        email: "test@example.com",
        password: "StrongPass1!",
        full_name: "Test User",
      });
      expect(tokenStorage.set).toHaveBeenCalledWith("test-token");
      expect(result).toEqual(mockAuthResponse);
    });
  });

  describe("forgotPassword", () => {
    it("posts to /auth/forgot-password with skipAuthRefresh", async () => {
      const mockResponse = { status: "ok", message: "Email sent" };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockResponse });

      const result = await authService.forgotPassword({ email: "test@example.com" });

      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/forgot-password",
        { email: "test@example.com" },
        { skipAuthRefresh: true },
      );
      expect(result).toEqual(mockResponse);
    });
  });

  describe("resetPassword", () => {
    it("posts to /auth/reset-password with skipAuthRefresh", async () => {
      const mockResponse = { status: "ok", message: "Password reset" };
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: mockResponse });

      const result = await authService.resetPassword({ token: "abc123", password: "NewStrongPass1!" });

      expect(apiClient.post).toHaveBeenCalledWith(
        "/auth/reset-password",
        { token: "abc123", password: "NewStrongPass1!" },
        { skipAuthRefresh: true },
      );
      expect(result).toEqual(mockResponse);
    });
  });

  describe("refresh", () => {
    it("calls refreshSession", async () => {
      vi.mocked(refreshSession).mockResolvedValueOnce(mockAuthResponse);

      const result = await authService.refresh();

      expect(refreshSession).toHaveBeenCalledOnce();
      expect(result).toEqual(mockAuthResponse);
    });

    it("returns null when refresh fails", async () => {
      vi.mocked(refreshSession).mockResolvedValueOnce(null);

      const result = await authService.refresh();

      expect(result).toBeNull();
    });
  });

  describe("logout", () => {
    it("posts to /auth/logout and clears token", async () => {
      vi.mocked(apiClient.post).mockResolvedValueOnce({ data: {} });

      await authService.logout();

      expect(apiClient.post).toHaveBeenCalledWith("/auth/logout");
      expect(tokenStorage.clear).toHaveBeenCalledOnce();
    });

    it("clears token even if logout request fails", async () => {
      vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("Network error"));

      try {
        await authService.logout();
      } catch {}

      expect(tokenStorage.clear).toHaveBeenCalledOnce();
    });
  });
});
