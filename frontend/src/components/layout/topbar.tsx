"use client";

import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Laptop, LogOut, Moon, Sparkles, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/stores/auth-store";

const themeIcons = {
  system: Laptop,
  light: Sun,
  dark: Moon,
} as const;

export function Topbar() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { user, clear } = useAuthStore();

  const ThemeIcon = theme ? themeIcons[theme as keyof typeof themeIcons] ?? Laptop : Laptop;

  return (
    <header className="glass-strong sticky top-0 z-20 flex h-16 items-center gap-3 border-b px-4">
      <div className="flex items-center gap-3 lg:hidden">
        <span className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground"><Sparkles className="h-5 w-5" /></span>
        <span className="font-semibold">Job Assistant</span>
      </div>
      <div className="flex-1" />
      <Button
        variant="ghost"
        size="icon"
        aria-label="Cycle theme"
        title={`Theme: ${theme ?? "system"}`}
        onClick={() => setTheme(theme === "system" ? "light" : theme === "light" ? "dark" : "system")}
      >
        <AnimatePresence mode="wait">
          <motion.span
            key={theme ?? "system"}
            initial={{ rotate: -90, opacity: 0, scale: 0.5 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: 90, opacity: 0, scale: 0.5 }}
            transition={{ type: "spring", stiffness: 260, damping: 20 }}
          >
            <ThemeIcon className="h-4 w-4" />
          </motion.span>
        </AnimatePresence>
      </Button>
      <div className="hidden text-right text-sm md:block">
        <div className="font-medium">{user?.full_name || user?.email || "Signed in"}</div>
        <div className="text-xs text-muted-foreground">{user?.email}</div>
      </div>
      <Button variant="ghost" size="icon" aria-label="Sign out" onClick={() => { authService.logout(); clear(); router.replace("/login"); }}>
        <LogOut className="h-4 w-4" />
      </Button>
    </header>
  );
}
