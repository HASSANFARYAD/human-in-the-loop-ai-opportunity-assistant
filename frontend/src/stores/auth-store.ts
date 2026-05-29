"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User, Workspace } from "@/types/api";

interface AuthState {
  user: User | null;
  activeWorkspace: Workspace | null;
  setUser: (user: User | null) => void;
  setActiveWorkspace: (workspace: Workspace | null) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      activeWorkspace: null,
      setUser: (user) => set({ user }),
      setActiveWorkspace: (activeWorkspace) => set({ activeWorkspace }),
      clear: () => set({ user: null, activeWorkspace: null }),
    }),
    { name: "job-assistant-session" },
  ),
);
