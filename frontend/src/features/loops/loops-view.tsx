"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import {
  AlertTriangle, CheckCircle2, Play, Repeat, Plus, Settings,
  Trash2, DollarSign, Target, Search, Globe, Clock, Power, PowerOff, Activity,
} from "lucide-react";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { loopsService } from "@/services/loops.service";
import { formatDate } from "@/lib/utils";
import { staggerItem } from "@/lib/animation";
import type { Loop, LoopRun, AutoApplyLog, AutoApplyHealth } from "@/types/api";

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1, delayChildren: 0.1 } },
};

export function LoopsView() {
  const activeTab = useSearchParams().get("tab") ?? "loops";
  const queryClient = useQueryClient();
  const [editingLoop, setEditingLoop] = useState<Partial<Loop> | null>(null);
  const [showForm, setShowForm] = useState(false);

  const loops = useQuery({ queryKey: ["loops"], queryFn: () => loopsService.list(true) });
  const stats = useQuery({ queryKey: ["auto-apply-stats"], queryFn: () => loopsService.autoApplyStats() });
  const dailyCount = useQuery({ queryKey: ["daily-apply-count"], queryFn: () => loopsService.dailyApplyCount() });
  const pendingApproval = useQuery({ queryKey: ["pending-approval"], queryFn: () => loopsService.pendingApproval() });
  const logs = useQuery({ queryKey: ["auto-apply-logs"], queryFn: () => loopsService.autoApplyLogs(50) });
  const health = useQuery({ queryKey: ["auto-apply-health"], queryFn: () => loopsService.health() });

  const runMutation = useMutation({
    mutationFn: (id: number) => loopsService.run(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["loops"] }); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => loopsService.delete(id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["loops"] }); },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => loopsService.update(id, { is_active }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["loops"] }); },
  });

  const isLoading = loops.isLoading || stats.isLoading;

  return (
    <motion.div variants={container} initial="hidden" animate="visible" className="space-y-5">
      <motion.div variants={staggerItem} className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Auto-Pilot Loops</h1>
          <p className="text-sm text-muted-foreground">Saved search configurations with automatic application scheduling.</p>
        </div>
        <Button onClick={() => { setEditingLoop({}); setShowForm(true); }}>
          <Plus className="mr-2 h-4 w-4" /> New Loop
        </Button>
      </motion.div>

      <motion.div variants={staggerItem} className="grid gap-4 md:grid-cols-5">
        <Card><CardContent className="p-5"><Repeat className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{(loops.data ?? []).length}</div><div className="text-sm text-muted-foreground">Total Loops</div></CardContent></Card>
        <Card><CardContent className="p-5"><Play className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{(loops.data ?? []).filter(l => l.auto_apply_enabled && l.is_active).length}</div><div className="text-sm text-muted-foreground">Active Auto-Pilot</div></CardContent></Card>
        <Card><CardContent className="p-5"><CheckCircle2 className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{dailyCount.data?.count ?? 0}</div><div className="text-sm text-muted-foreground">Applied Today</div></CardContent></Card>
        <Card><CardContent className="p-5"><AlertTriangle className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{stats.data?.failed ?? 0}</div><div className="text-sm text-muted-foreground">Failed (30d)</div></CardContent></Card>
        <Card><CardContent className="p-5"><Clock className="mb-3 h-5 w-5 text-muted-foreground" /><div className="text-2xl font-semibold">{pendingApproval.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Needs Approval</div></CardContent></Card>
      </motion.div>

      <div className="flex gap-2 border-b pb-2">
        <TabButton href="?tab=loops" active={activeTab === "loops"}>Loops</TabButton>
        <TabButton href="?tab=monitoring" active={activeTab === "monitoring"}>Monitoring</TabButton>
        <TabButton href="?tab=stats" active={activeTab === "stats"}>Stats</TabButton>
        <TabButton href="?tab=logs" active={activeTab === "logs"}>Logs</TabButton>
      </div>

      {activeTab === "monitoring" ? (
        <motion.div variants={staggerItem}>
          <MonitoringView health={health.data} isLoading={health.isLoading} />
        </motion.div>
      ) : activeTab === "logs" ? (
        <motion.div variants={staggerItem}>
          <AutoApplyLogsView logs={logs.data ?? []} isLoading={logs.isLoading} />
        </motion.div>
      ) : activeTab === "stats" ? (
        <motion.div variants={staggerItem}>
          <StatsView stats={stats.data} />
        </motion.div>
      ) : (
        <motion.div variants={staggerItem} className="space-y-4">
          {isLoading ? (
            <div className="flex justify-center py-12"><Spinner /></div>
          ) : (loops.data ?? []).length === 0 ? (
            <Card><CardContent className="flex flex-col items-center gap-3 py-12 text-center"><Repeat className="h-12 w-12 text-muted-foreground" /><p className="text-muted-foreground">No loops yet. Create your first auto-pilot loop to start automating job applications.</p></CardContent></Card>
          ) : (
            (loops.data ?? []).map((loop) => (
              <LoopCard
                key={loop.id ?? loop.loop_id}
                loop={loop}
                onRun={() => runMutation.mutate(loop.id ?? loop.loop_id)}
                onToggle={() => toggleMutation.mutate({ id: loop.id ?? loop.loop_id, is_active: !loop.is_active })}
                onDelete={() => { if (confirm("Delete this loop?")) deleteMutation.mutate(loop.id ?? loop.loop_id); }}
                onEdit={() => { setEditingLoop(loop); setShowForm(true); }}
              />
            ))
          )}
        </motion.div>
      )}

      {showForm && (
        <LoopFormModal
          initial={editingLoop ?? {}}
          onClose={() => { setShowForm(false); setEditingLoop(null); }}
          onSaved={() => { setShowForm(false); setEditingLoop(null); queryClient.invalidateQueries({ queryKey: ["loops"] }); }}
        />
      )}
    </motion.div>
  );
}

function LoopCard({ loop, onRun, onToggle, onDelete, onEdit }: { loop: Loop; onRun: () => void; onToggle: () => void; onDelete: () => void; onEdit: () => void }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex items-center gap-3">
              <h3 className="font-semibold truncate">{loop.name}</h3>
              <Badge>{loop.is_active ? "active" : "inactive"}</Badge>
              {loop.auto_apply_enabled && loop.is_active && <Badge className="bg-primary text-primary-foreground">auto-pilot</Badge>}
            </div>
            {loop.search_query && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Search className="h-3.5 w-3.5" />
                <span className="truncate">{loop.search_query}</span>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1"><Globe className="h-3.5 w-3.5" />{(loop.sources ?? []).join(", ")}</span>
              <span className="flex items-center gap-1"><Target className="h-3.5 w-3.5" />Score &ge; {loop.min_score_threshold}</span>
              <span className="flex items-center gap-1"><DollarSign className="h-3.5 w-3.5" />{loop.daily_budget}/day</span>
              <span className="flex items-center gap-1"><Clock className="h-3.5 w-3.5" />Every {loop.schedule_interval_hours}h{loop.last_run_at ? ` · Last: ${formatDate(loop.last_run_at)}` : ""}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button size="sm" variant="outline" onClick={onRun} title="Run now"><Play className="h-4 w-4" /></Button>
            <Button size="sm" variant="outline" onClick={onToggle} title={loop.is_active ? "Disable" : "Enable"}>{loop.is_active ? <PowerOff className="h-4 w-4" /> : <Power className="h-4 w-4" />}</Button>
            <Button size="sm" variant="outline" onClick={onEdit} title="Edit"><Settings className="h-4 w-4" /></Button>
            <Button size="sm" variant="outline" onClick={onDelete} title="Delete"><Trash2 className="h-4 w-4" /></Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AutoApplyLogsView({ logs, isLoading }: { logs: AutoApplyLog[]; isLoading: boolean }) {
  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>;
  if (logs.length === 0) return <Card><CardContent className="py-12 text-center text-muted-foreground">No application logs yet.</CardContent></Card>;
  return (
    <Card>
      <CardHeader><CardTitle>Application Logs</CardTitle></CardHeader>
      <CardContent className="space-y-2">
        {logs.map((log) => (
          <div key={log.id ?? log.auto_apply_log_id} className="flex items-center justify-between rounded-md border p-3 text-sm">
            <div>
              <span className="font-medium">Job #{log.job_id}</span>
              <span className="text-muted-foreground"> · {log.channel}</span>
              {log.score != null && <span className="text-muted-foreground"> · Score: {log.score}</span>}
              <div className="text-xs text-muted-foreground">{formatDate(log.created_at)}{log.error_message ? ` · ${log.error_message}` : ""}</div>
            </div>
            <StatusBadge status={log.status} />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function StatsView({ stats }: { stats: { total?: number; submitted?: number; failed?: number; skipped?: number; budget_exceeded?: number } | undefined }) {
  if (!stats) return <div className="flex justify-center py-12"><Spinner /></div>;
  const items = [
    { label: "Total", value: stats.total ?? 0, color: "text-primary" },
    { label: "Submitted", value: stats.submitted ?? 0, color: "text-success" },
    { label: "Failed", value: stats.failed ?? 0, color: "text-destructive" },
    { label: "Skipped", value: stats.skipped ?? 0, color: "text-warning" },
    { label: "Budget Exceeded", value: stats.budget_exceeded ?? 0, color: "text-muted-foreground" },
  ];
  return (
    <div className="grid gap-4 md:grid-cols-5">
      {items.map((item) => (
        <Card key={item.label}>
          <CardContent className="p-5 text-center">
            <div className={`text-3xl font-bold ${item.color}`}>{item.value}</div>
            <div className="text-sm text-muted-foreground">{item.label}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; className: string }> = {
    submitted: { label: "Submitted", className: "bg-primary text-primary-foreground" },
    pending: { label: "Pending", className: "bg-muted text-muted-foreground" },
    failed: { label: "Failed", className: "bg-destructive text-destructive-foreground" },
    skipped: { label: "Skipped", className: "" },
    budget_exceeded: { label: "Budget Exceeded", className: "" },
    needs_approval: { label: "Needs Approval", className: "bg-muted text-muted-foreground" },
  };
  const config = map[status] ?? { label: status, className: "" };
  return <Badge className={config.className}>{config.label}</Badge>;
}

function TabButton({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <a href={href} className={`px-3 py-1.5 text-sm rounded-md transition-colors ${active ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>
      {children}
    </a>
  );
}

function MonitoringView({ health, isLoading }: { health: AutoApplyHealth | undefined; isLoading: boolean }) {
  if (isLoading) return <div className="flex justify-center py-12"><Spinner /></div>;
  if (!health) return <Card><CardContent className="py-12 text-center text-muted-foreground">No health data available.</CardContent></Card>;

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-4">
        <Card><CardContent className="p-5 flex items-center gap-4"><div className={`rounded-full p-2 ${health.status === "healthy" ? "bg-success/10" : health.status === "degraded" ? "bg-warning/10" : "bg-destructive/10"}`}><Activity className={`h-5 w-5 ${health.status === "healthy" ? "text-success" : health.status === "degraded" ? "text-warning" : "text-destructive"}`} /></div><div><div className="text-xl font-semibold capitalize">{health.status}</div><div className="text-xs text-muted-foreground">System Status</div></div></CardContent></Card>
        <Card><CardContent className="p-5 flex items-center gap-4"><div className="rounded-full bg-primary/10 p-2"><Repeat className="h-5 w-5 text-primary" /></div><div><div className="text-xl font-semibold">{health.loops.active}/{health.loops.total}</div><div className="text-xs text-muted-foreground">Active Loops</div></div></CardContent></Card>
        <Card><CardContent className="p-5 flex items-center gap-4"><div className="rounded-full bg-success/10 p-2"><CheckCircle2 className="h-5 w-5 text-success" /></div><div><div className="text-xl font-semibold">{health.runs.success_rate_pct}%</div><div className="text-xs text-muted-foreground">Success Rate (7d)</div></div></CardContent></Card>
        <Card><CardContent className="p-5 flex items-center gap-4"><div className="rounded-full bg-muted p-2"><DollarSign className="h-5 w-5 text-muted-foreground" /></div><div><div className="text-xl font-semibold">{health.loops.budget_remaining}/{health.loops.today_budget}</div><div className="text-xs text-muted-foreground">Budget Remaining</div></div></CardContent></Card>
      </div>

      {health.warnings.length > 0 && (
        <Card className="border-warning/50">
          <CardContent className="p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
              <div className="space-y-1">
                <p className="text-sm font-medium">Warnings</p>
                {health.warnings.map((w, i) => <p key={i} className="text-sm text-muted-foreground">{w}</p>)}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Source Health</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {health.circuit_breaker.total_sources === 0 ? (
              <p className="text-sm text-muted-foreground">No sources configured.</p>
            ) : (
              <>
                <div className="flex items-center gap-2 text-sm">
                  <div className="h-2 w-2 rounded-full bg-success" />
                  <span className="text-muted-foreground">{health.circuit_breaker.total_sources - health.circuit_breaker.open - health.circuit_breaker.degraded} healthy</span>
                  {health.circuit_breaker.degraded > 0 && <><div className="h-2 w-2 rounded-full bg-warning" /><span className="text-muted-foreground">{health.circuit_breaker.degraded} degraded</span></>}
                  {health.circuit_breaker.open > 0 && <><div className="h-2 w-2 rounded-full bg-destructive" /><span className="text-muted-foreground">{health.circuit_breaker.open} open</span></>}
                </div>
                {health.circuit_breaker.open_sources.length > 0 && (
                  <div className="pt-2 space-y-1">
                    <p className="text-xs font-medium text-destructive">Open circuits:</p>
                    {health.circuit_breaker.open_sources.map(s => (
                      <div key={s.source} className="flex items-center justify-between rounded-md border border-destructive/20 bg-destructive/5 px-3 py-1.5 text-sm">
                        <span className="font-medium">{s.source}</span>
                        <span className="text-xs text-muted-foreground">cooldown {Math.round(s.cooldown_remaining_s)}s</span>
                      </div>
                    ))}
                  </div>
                )}
                {health.circuit_breaker.degraded_sources.length > 0 && (
                  <div className="pt-2 space-y-1">
                    <p className="text-xs font-medium text-warning">Degraded sources:</p>
                    {health.circuit_breaker.degraded_sources.map(s => (
                      <div key={s.source} className="flex items-center justify-between rounded-md border border-warning/20 bg-warning/5 px-3 py-1.5 text-sm">
                        <span className="font-medium">{s.source}</span>
                        <span className="text-xs text-muted-foreground">{s.failures} failure(s)</span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Recent Runs (7d)</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Total runs</span>
                <span className="font-semibold">{health.runs.total_last_7d}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Successful</span>
                <span className="font-semibold text-success">{health.runs.success}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Failed</span>
                <span className="font-semibold text-destructive">{health.runs.failed}</span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Errors</span>
                <span className="font-semibold text-warning">{health.runs.errors}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm font-medium">Daily Budget Utilization</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Usage</span>
              <span className="font-semibold">{health.loops.today_usage} / {health.loops.today_budget}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full transition-all ${health.loops.today_budget > 0 && health.loops.today_usage >= health.loops.today_budget ? "bg-destructive" : health.loops.today_budget > 0 && (health.loops.today_usage / health.loops.today_budget) > 0.8 ? "bg-warning" : "bg-success"}`}
                style={{ width: `${health.loops.today_budget > 0 ? Math.min(100, (health.loops.today_usage / health.loops.today_budget) * 100) : 0}%` }}
              />
            </div>
            {health.loops.today_budget > 0 && health.loops.today_usage >= health.loops.today_budget && (
              <p className="text-xs text-destructive">Daily budget exhausted — loops will skip until tomorrow.</p>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={() => loopsService.resetCircuitBreaker()}>
          Reset All Circuit Breakers
        </Button>
      </div>
    </div>
  );
}

function LoopFormModal({ initial, onClose, onSaved }: { initial: Partial<Loop>; onClose: () => void; onSaved: () => void }) {
  const queryClient = useQueryClient();
  const isEditing = !!initial.id;
  const [form, setForm] = useState({
    name: initial.name ?? "",
    search_query: initial.search_query ?? "",
    sources: (initial.sources ?? ["LinkedIn", "RemoteJobs.org"]).join(", "),
    platforms: (initial.platforms ?? ["linkedin", "email"]).join(", "),
    channels: (initial.channels ?? ["linkedin"]).join(", "),
    is_active: initial.is_active ?? true,
    auto_apply_enabled: initial.auto_apply_enabled ?? false,
    daily_budget: initial.daily_budget ?? 10,
    max_applications_per_run: initial.max_applications_per_run ?? 5,
    min_score_threshold: initial.min_score_threshold ?? 60,
    schedule_interval_hours: initial.schedule_interval_hours ?? 6,
  });

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...form,
        sources: form.sources.split(",").map(s => s.trim()).filter(Boolean),
        platforms: form.platforms.split(",").map(s => s.trim()).filter(Boolean),
        channels: form.channels.split(",").map(s => s.trim()).filter(Boolean),
      };
      if (isEditing) {
        return loopsService.update(initial.id!, payload);
      }
      return loopsService.create(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["loops"] });
      onSaved();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl border bg-background p-6 shadow-lg" onClick={e => e.stopPropagation()}>
        <h2 className="mb-4 text-lg font-semibold">{isEditing ? "Edit Loop" : "New Loop"}</h2>
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">Name</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Senior Frontend Roles" />
            </div>
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium">Search Query</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" value={form.search_query} onChange={e => setForm(p => ({ ...p, search_query: e.target.value }))} placeholder="e.g. senior frontend engineer react remote" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Sources (comma-separated)</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" value={form.sources} onChange={e => setForm(p => ({ ...p, sources: e.target.value }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Channels (comma-separated)</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" value={form.channels} onChange={e => setForm(p => ({ ...p, channels: e.target.value }))} placeholder="linkedin, email" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Daily Budget</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" type="number" value={form.daily_budget} onChange={e => setForm(p => ({ ...p, daily_budget: parseInt(e.target.value) || 0 }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Max Per Run</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" type="number" value={form.max_applications_per_run} onChange={e => setForm(p => ({ ...p, max_applications_per_run: parseInt(e.target.value) || 1 }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Min Score</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" type="number" value={form.min_score_threshold} onChange={e => setForm(p => ({ ...p, min_score_threshold: parseInt(e.target.value) || 0 }))} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Interval (hours)</label>
              <input className="w-full rounded-md border bg-transparent px-3 py-2 text-sm" type="number" value={form.schedule_interval_hours} onChange={e => setForm(p => ({ ...p, schedule_interval_hours: parseInt(e.target.value) || 1 }))} />
            </div>
            <div className="col-span-2 flex gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={e => setForm(p => ({ ...p, is_active: e.target.checked }))} />
                Active
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.auto_apply_enabled} onChange={e => setForm(p => ({ ...p, auto_apply_enabled: e.target.checked }))} />
                Auto-Apply Enabled
              </label>
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving..." : isEditing ? "Update" : "Create"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
