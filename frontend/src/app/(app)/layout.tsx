"use client";

import { useEffect, useState } from "react";
import { Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MobileNav, Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { PageTransition } from "@/components/ui/page-transition";
import { Spinner } from "@/components/ui/spinner";
import { authService } from "@/services/auth.service";
import { workspaceService } from "@/services/workspace.service";
import { useAuthStore } from "@/stores/auth-store";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { setUser, setActiveWorkspace } = useAuthStore();
  const [authReady, setAuthReady] = useState(false);
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authService.refresh().then((session) => {
      if (cancelled) return;
      if (session) {
        setUser(session.user);
        setHasSession(true);
        queryClient.prefetchQuery({
          queryKey: ["enterprise-bootstrap"],
          queryFn: workspaceService.bootstrap,
        });
      }
      setAuthReady(true);
      if (!session) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const bootstrap = useQuery({
    queryKey: ["enterprise-bootstrap"],
    queryFn: workspaceService.bootstrap,
    enabled: authReady && hasSession,
  });

  useEffect(() => {
    if (bootstrap.data?.workspace) setActiveWorkspace(bootstrap.data.workspace);
  }, [bootstrap.data, setActiveWorkspace]);

  if (!authReady) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Spinner className="h-8 w-8 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Verifying session...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen overflow-x-hidden bg-transparent">
      <Suspense fallback={null}>
        <Sidebar />
      </Suspense>
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64 xl:pl-72">
        <Topbar />
        <Suspense fallback={null}>
          <MobileNav />
        </Suspense>
        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-4 md:p-6"><PageTransition>{children}</PageTransition></main>
      </div>
    </div>
  );
}
