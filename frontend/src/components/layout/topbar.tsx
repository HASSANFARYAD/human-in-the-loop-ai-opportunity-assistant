"use client";

import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { Laptop, LogOut, Moon, Sparkles, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/stores/auth-store";

export function Topbar() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { user, clear } = useAuthStore();

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
        {theme === "system" ? <Laptop className="h-4 w-4" /> : theme === "dark" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
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
