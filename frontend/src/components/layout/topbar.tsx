"use client";

import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { LogOut, Moon, Search, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/stores/auth-store";

export function Topbar() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { user, clear } = useAuthStore();

  return (
    <header className="glass-strong sticky top-0 z-20 flex h-16 items-center gap-3 border-b px-4">
      <div className="relative max-w-xl flex-1">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search opportunities, automations, providers..." />
      </div>
      <Button variant="ghost" size="icon" aria-label="Toggle theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
        <Sun className="h-4 w-4 rotate-0 scale-100 transition dark:-rotate-90 dark:scale-0" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition dark:rotate-0 dark:scale-100" />
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
