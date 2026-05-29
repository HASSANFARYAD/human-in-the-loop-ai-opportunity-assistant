"use client";

import { useEffect } from "react";
import { Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { authService } from "@/services/auth.service";
import { workspaceService } from "@/services/workspace.service";
import { tokenStorage } from "@/services/client";
import { useAuthStore } from "@/stores/auth-store";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { setUser, setActiveWorkspace } = useAuthStore();
  const hasToken = typeof window !== "undefined" && Boolean(tokenStorage.get());

  useEffect(() => {
    if (!hasToken) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [hasToken, pathname, router]);

  const me = useQuery({
    queryKey: ["me"],
    queryFn: authService.me,
    enabled: hasToken,
  });

  const bootstrap = useQuery({
    queryKey: ["enterprise-bootstrap"],
    queryFn: workspaceService.bootstrap,
    enabled: hasToken,
  });

  useEffect(() => {
    if (me.data) setUser(me.data);
  }, [me.data, setUser]);

  useEffect(() => {
    if (bootstrap.data?.workspace) setActiveWorkspace(bootstrap.data.workspace);
  }, [bootstrap.data, setActiveWorkspace]);

  return (
    <div className="flex min-h-screen bg-background">
      <Suspense fallback={null}>
        <Sidebar />
      </Suspense>
      <div className="min-w-0 flex-1">
        <Topbar />
        <main className="mx-auto w-full max-w-7xl p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
