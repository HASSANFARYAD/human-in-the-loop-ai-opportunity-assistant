"use client";

import { useEffect, useState } from "react";
import { Suspense } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { MobileNav, Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { authService } from "@/services/auth.service";
import { workspaceService } from "@/services/workspace.service";
import { useAuthStore } from "@/stores/auth-store";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { setUser, setActiveWorkspace } = useAuthStore();
  const [authReady, setAuthReady] = useState(false);
  const [hasSession, setHasSession] = useState(false);

  useEffect(() => {
    let cancelled = false;
    authService.refresh().then((ok) => {
      if (cancelled) return;
      setHasSession(ok);
      setAuthReady(true);
      if (!ok) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const me = useQuery({
    queryKey: ["me"],
    queryFn: authService.me,
    enabled: authReady && hasSession,
  });

  const bootstrap = useQuery({
    queryKey: ["enterprise-bootstrap"],
    queryFn: workspaceService.bootstrap,
    enabled: authReady && hasSession,
  });

  useEffect(() => {
    if (me.data) setUser(me.data);
  }, [me.data, setUser]);

  useEffect(() => {
    if (bootstrap.data?.workspace) setActiveWorkspace(bootstrap.data.workspace);
  }, [bootstrap.data, setActiveWorkspace]);

  if (!authReady) return null;

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
        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
