import { describe, it, expect, beforeEach } from "vitest";
import { useAuthStore } from "@/stores/auth-store";
import type { User, Workspace } from "@/types/api";

const mockUser: User = { id: 1, email: "test@example.com", full_name: "Test" };
const mockWorkspace: Workspace = { id: 1, name: "Default", role: "owner" };

describe("authStore", () => {
  beforeEach(() => {
    const state = useAuthStore.getState();
    state.clear();
  });

  it("starts with null user and workspace", () => {
    const { user, activeWorkspace } = useAuthStore.getState();
    expect(user).toBeNull();
    expect(activeWorkspace).toBeNull();
  });

  it("setUser updates the user", () => {
    useAuthStore.getState().setUser(mockUser);
    const { user } = useAuthStore.getState();
    expect(user).toEqual(mockUser);
  });

  it("setUser accepts null", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().setUser(null);
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("setActiveWorkspace updates workspace", () => {
    useAuthStore.getState().setActiveWorkspace(mockWorkspace);
    const { activeWorkspace } = useAuthStore.getState();
    expect(activeWorkspace).toEqual(mockWorkspace);
  });

  it("clear resets user and workspace to null", () => {
    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().setActiveWorkspace(mockWorkspace);
    useAuthStore.getState().clear();
    const { user, activeWorkspace } = useAuthStore.getState();
    expect(user).toBeNull();
    expect(activeWorkspace).toBeNull();
  });

  it("persists to localStorage under job-assistant-session", () => {
    const key = "job-assistant-session";
    localStorage.removeItem(key);
    useAuthStore.getState().setUser(mockUser);
    const stored = JSON.parse(localStorage.getItem(key) ?? "{}");
    expect(stored.state.user).toEqual(mockUser);
  });
});
