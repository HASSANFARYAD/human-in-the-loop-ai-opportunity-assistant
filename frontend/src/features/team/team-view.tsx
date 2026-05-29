"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Building2, ShieldCheck, Users } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { workspaceService } from "@/services/workspace.service";
import { useAuthStore } from "@/stores/auth-store";

export function TeamView() {
  const tab = useSearchParams().get("tab") ?? "workspaces";
  const active = useAuthStore((s) => s.activeWorkspace);
  const workspaces = useQuery({ queryKey: ["workspaces"], queryFn: workspaceService.list });
  const members = useQuery({ queryKey: ["members", active?.id], queryFn: () => workspaceService.members(active!.id), enabled: Boolean(active?.id) });
  const permissions = useQuery({ queryKey: ["permissions"], queryFn: workspaceService.permissions });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Team</h1><p className="text-sm text-muted-foreground">Organizations, workspaces, members, roles, permissions, and workspace isolation.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="p-5"><Building2 className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{workspaces.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Workspaces</div></CardContent></Card>
        <Card><CardContent className="p-5"><Users className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{members.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Members</div></CardContent></Card>
        <Card><CardContent className="p-5"><ShieldCheck className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{Object.keys(permissions.data ?? {}).length}</div><div className="text-sm text-muted-foreground">Permission groups</div></CardContent></Card>
      </div>
      {tab === "members" ? (
        <Card><CardHeader><CardTitle>Members</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(members.data ?? [], null, 2)}</pre></CardContent></Card>
      ) : tab === "organizations" ? (
        <Card><CardHeader><CardTitle>Organizations and Permissions</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(permissions.data ?? {}, null, 2)}</pre></CardContent></Card>
      ) : (
        <Card><CardHeader><CardTitle>Workspaces</CardTitle></CardHeader><CardContent className="space-y-3">{(workspaces.data ?? []).map((workspace) => <div key={workspace.id} className="flex items-center justify-between rounded-md border p-3"><div><div className="font-medium">{workspace.name}</div><div className="text-sm text-muted-foreground">{workspace.description || "No description"}</div></div><Badge>{workspace.role || "member"}</Badge></div>)}</CardContent></Card>
      )}
    </div>
  );
}
