"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Activity, Bot, Database, HeartPulse, Mail, Save, ShieldCheck, TestTube2 } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DataFields, DataTable } from "@/components/ui/data-display";
import { auditService } from "@/services/audit.service";
import { feedbackService } from "@/services/feedback.service";
import { opportunityService } from "@/services/opportunity.service";
import { providerService } from "@/services/provider.service";
import type { AdminConfig, Profile } from "@/types/api";

export function SettingsView() {
  const tab = useSearchParams().get("tab") ?? "settings";
  const audit = useQuery({ queryKey: ["audit"], queryFn: () => auditService.logs() });
  const health = useQuery({ queryKey: ["health"], queryFn: auditService.health });
  const usage = useQuery({ queryKey: ["usage"], queryFn: auditService.usage });
  const feedback = useQuery({ queryKey: ["feedback"], queryFn: () => feedbackService.list() });
  const adminConfigs = useQuery({ queryKey: ["admin-configs"], queryFn: providerService.adminConfigs });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Settings</h1><p className="text-sm text-muted-foreground">Manage your resume profile, AI provider, Gmail import, and app preferences.</p></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Card><CardContent className="p-5"><HeartPulse className="mb-3 h-5 w-5 text-success" /><div className="text-2xl font-semibold">{String(health.data?.status ?? "unknown")}</div><div className="text-sm text-muted-foreground">Health</div></CardContent></Card>
        <Card><CardContent className="p-5"><ShieldCheck className="mb-3 h-5 w-5 text-primary" /><div className="text-2xl font-semibold">{audit.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Account events</div></CardContent></Card>
        <Card><CardContent className="p-5"><Activity className="mb-3 h-5 w-5 text-warning" /><div className="text-2xl font-semibold">{feedback.data?.length ?? 0}</div><div className="text-sm text-muted-foreground">Feedback items</div></CardContent></Card>
      </div>
      {tab === "profile" ? (
        <ProfileManager />
      ) : tab === "feedback" ? (
        <Card><CardHeader><CardTitle>Feedback</CardTitle></CardHeader><CardContent><DataTable rows={(feedback.data ?? []) as unknown as Record<string, unknown>[]} columns={["title", "category", "severity", "status", "created_at"]} /></CardContent></Card>
      ) : tab === "audit" ? (
        <Card><CardHeader><CardTitle>Audit Logs</CardTitle></CardHeader><CardContent><DataTable rows={(audit.data ?? []) as unknown as Record<string, unknown>[]} columns={["created_at", "action", "resource_type", "resource_id"]} /></CardContent></Card>
      ) : tab === "usage" ? (
        <Card><CardHeader><CardTitle>Usage</CardTitle></CardHeader><CardContent><DataFields data={usage.data ?? {}} /></CardContent></Card>
      ) : tab === "health" ? (
        <Card><CardHeader><CardTitle>Health</CardTitle></CardHeader><CardContent><DataFields data={health.data ?? {}} /></CardContent></Card>
      ) : (
        <AdminConfiguration data={adminConfigs.data} loading={adminConfigs.isLoading} />
      )}
    </div>
  );
}

const CONFIG_TYPES = [
  { type: "ai_provider", title: "AI Provider Settings", icon: Bot, defaults: { provider: "openai", model: "gpt-4o-mini", base_url: "", timeout_seconds: 60 } },
  { type: "gmail", title: "Gmail OAuth Settings", icon: Mail, defaults: { client_id: "", redirect_uri: "http://localhost:8000/api/v1/gmail/oauth/callback", scopes: "https://www.googleapis.com/auth/gmail.readonly" } },
  { type: "recording_storage", title: "Recording Storage Settings", icon: Database, defaults: { storage_type: "local", storage_path: "data/recordings", max_upload_size: 26214400, allowed_mime_types: "audio/webm,audio/wav,audio/mpeg,audio/mp4,audio/ogg" } },
] as const;

function AdminConfiguration({ data, loading }: { data?: { configs: AdminConfig[]; statuses: Record<string, { status: string; configured: boolean; count: number; active_count: number }> }; loading: boolean }) {
  const configs = data?.configs ?? [];
  const statuses = data?.statuses ?? {};
  // AI provider configuration lives on the dedicated AI Provider page to avoid two
  // competing config surfaces; Settings manages only Gmail and recording storage here.
  const serviceConfigTypes = CONFIG_TYPES.filter((item) => item.type !== "ai_provider");
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold">Connected Services</h2>
        <p className="text-sm text-muted-foreground">Manage the services used for Gmail import and recording upload. Your AI provider is configured on its own page.</p>
      </div>
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <div className="flex items-center gap-3">
            <Bot className="h-5 w-5 text-primary" />
            <div>
              <div className="font-medium">AI Provider</div>
              <div className="text-xs text-muted-foreground">Set your AI key and model (OpenAI, Azure OpenAI, Claude, Gemini, and more).</div>
            </div>
          </div>
          <Button asChild variant="outline"><Link href="/integrations?service=ai_provider">Configure AI Provider</Link></Button>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        {serviceConfigTypes.map((item) => {
          const Icon = item.icon;
          const status = statuses[item.type]?.status ?? "missing";
          return (
            <Card key={item.type}>
              <CardContent className="p-5">
                <Icon className="mb-3 h-5 w-5 text-primary" />
                <div className="font-medium">{item.title.replace(" Settings", "")}</div>
                <div className="mt-2 text-2xl font-semibold capitalize">{loading ? "loading" : status}</div>
                <div className="text-xs text-muted-foreground">{statuses[item.type]?.active_count ?? 0} active / {statuses[item.type]?.count ?? 0} saved</div>
              </CardContent>
            </Card>
          );
        })}
      </div>
      {serviceConfigTypes.map((item) => <AdminConfigForm key={item.type} type={item.type} title={item.title} defaults={item.defaults} selected={configs.find((config) => config.type === item.type && config.is_active) ?? configs.find((config) => config.type === item.type)} />)}
    </div>
  );
}

function AdminConfigForm({ type, title, defaults, selected }: { type: AdminConfig["type"]; title: string; defaults: Record<string, unknown>; selected?: AdminConfig }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [secret, setSecret] = useState("");
  const [active, setActive] = useState(true);
  const [config, setConfig] = useState<Record<string, string>>({});
  useEffect(() => {
    const nextConfig = { ...defaults, ...(selected?.config ?? {}) };
    setName(selected?.name ?? (type === "ai_provider" ? "openai" : type));
    setDisplayName(selected?.display_name ?? "");
    setSecret("");
    setActive(selected?.is_active ?? true);
    setConfig(Object.fromEntries(Object.entries(nextConfig).map(([key, value]) => [key, String(value ?? "")])));
  }, [defaults, selected, type]);

  const save = useMutation({
    mutationFn: () => {
      const payload = { type, name, display_name: displayName, secret, config: serializeAdminConfig(type, config), is_active: active, keep_existing_secret_if_blank: true };
      return selected ? providerService.updateAdminConfig(type, selected.id, payload) : providerService.saveAdminConfig(payload);
    },
    onSuccess: () => {
      toast.success(`${title} saved`);
      setSecret("");
      qc.invalidateQueries({ queryKey: ["admin-configs"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const activate = useMutation({
    mutationFn: () => selected && selected.is_active ? providerService.deactivateAdminConfig(type, selected.id) : providerService.activateAdminConfig(type, selected?.id ?? name),
    onSuccess: () => {
      toast.success(selected?.is_active ? "Configuration deactivated" : "Configuration activated");
      qc.invalidateQueries({ queryKey: ["admin-configs"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const test = useMutation({
    mutationFn: () => providerService.testAdminConfig(type, selected?.id ?? name),
    onSuccess: (result) => toast.success(result.message),
    onError: (error) => toast.error(error.message),
  });
  const update = (key: string, value: string) => setConfig((current) => ({ ...current, [key]: value }));
  const requiresSecret = type !== "recording_storage";
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <Field label={type === "ai_provider" ? "Provider name" : "Configuration name"}><Input value={name} onChange={(event) => setName(event.target.value)} /></Field>
        <Field label="Display name"><Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder={selected?.display_name || title} /></Field>
        {requiresSecret ? <Field label={type === "gmail" ? "Client secret" : "API key"}><Input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder={selected?.has_secret ? "Saved secret is masked; enter a new value to replace it" : "Enter secret"} /></Field> : null}
        {type === "ai_provider" ? <AiAdminFields config={config} update={update} /> : null}
        {type === "gmail" ? <GmailAdminFields config={config} update={update} /> : null}
        {type === "recording_storage" ? <RecordingAdminFields config={config} update={update} /> : null}
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Active</label>
        <div className="flex flex-wrap items-center gap-3 md:col-span-2">
          <Button disabled={save.isPending || (requiresSecret && !secret && !selected?.has_secret)} onClick={() => save.mutate()}><Save className="h-4 w-4" /> Save</Button>
          <Button variant="outline" disabled={!selected || activate.isPending} onClick={() => activate.mutate()}>{selected?.is_active ? "Deactivate" : "Activate"}</Button>
          <Button variant="outline" disabled={!selected || test.isPending} onClick={() => test.mutate()}><TestTube2 className="h-4 w-4" /> Validate</Button>
          <span className="text-sm text-muted-foreground">{selected ? `${selected.is_active ? "Active" : "Inactive"} · ${selected.has_secret ? "secret stored" : "no secret stored"}` : "No saved config"}</span>
        </div>
      </CardContent>
    </Card>
  );
}

function AiAdminFields({ config, update }: { config: Record<string, string>; update: (key: string, value: string) => void }) {
  return <>
    <Field label="Model name"><Input value={config.model ?? ""} onChange={(event) => update("model", event.target.value)} /></Field>
    <Field label="Base URL"><Input value={config.base_url ?? ""} onChange={(event) => update("base_url", event.target.value)} placeholder="Optional OpenAI-compatible endpoint" /></Field>
    <Field label="Timeout seconds"><Input type="number" min={1} value={config.timeout_seconds ?? "60"} onChange={(event) => update("timeout_seconds", event.target.value)} /></Field>
    <Field label="Provider options JSON"><Textarea value={config.options_json ?? "{}"} onChange={(event) => update("options_json", event.target.value)} /></Field>
  </>;
}

function GmailAdminFields({ config, update }: { config: Record<string, string>; update: (key: string, value: string) => void }) {
  return <>
    <Field label="Google client ID"><Input value={config.client_id ?? ""} onChange={(event) => update("client_id", event.target.value)} /></Field>
    <Field label="Redirect URI"><Input value={config.redirect_uri ?? ""} onChange={(event) => update("redirect_uri", event.target.value)} /></Field>
    <Field label="Gmail scopes"><Input value={config.scopes ?? ""} onChange={(event) => update("scopes", event.target.value)} /></Field>
    <Field label="Provider options JSON"><Textarea value={config.options_json ?? "{}"} onChange={(event) => update("options_json", event.target.value)} /></Field>
  </>;
}

function RecordingAdminFields({ config, update }: { config: Record<string, string>; update: (key: string, value: string) => void }) {
  return <>
    <Field label="Storage type"><Input value={config.storage_type ?? "local"} onChange={(event) => update("storage_type", event.target.value)} /></Field>
    <Field label="Storage path"><Input value={config.storage_path ?? ""} onChange={(event) => update("storage_path", event.target.value)} /></Field>
    <Field label="Max upload size bytes"><Input type="number" min={1} value={config.max_upload_size ?? "26214400"} onChange={(event) => update("max_upload_size", event.target.value)} /></Field>
    <Field label="Allowed MIME types"><Input value={config.allowed_mime_types ?? ""} onChange={(event) => update("allowed_mime_types", event.target.value)} /></Field>
  </>;
}

function serializeAdminConfig(type: AdminConfig["type"], config: Record<string, string>) {
  const output: Record<string, unknown> = { ...config };
  if (type === "ai_provider") output.timeout_seconds = Number(config.timeout_seconds || 60);
  if (type === "recording_storage") output.max_upload_size = Number(config.max_upload_size || 26214400);
  if (config.options_json) {
    try {
      output.options = JSON.parse(config.options_json);
    } catch {
      throw new Error("Provider options JSON is invalid.");
    }
  }
  delete output.options_json;
  return output;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-2 text-sm font-medium">{label}{children}</label>;
}

function ProfileManager() {
  const qc = useQueryClient();
  const profiles = useQuery({ queryKey: ["profiles"], queryFn: opportunityService.profiles });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creatingNew, setCreatingNew] = useState(false);

  const list = useMemo(() => profiles.data ?? [], [profiles.data]);

  useEffect(() => {
    if (list.length && (selectedId === null || !list.some((p) => p.id === selectedId)) && !creatingNew) {
      const def = list.find((p) => p.is_default) ?? list[0];
      setSelectedId(def?.id ?? null);
    }
  }, [list, selectedId, creatingNew]);

  useEffect(() => {
    if (creatingNew && selectedId !== null && list.some((p) => p.id === selectedId)) {
      setCreatingNew(false);
    }
  }, [list, creatingNew, selectedId]);

  const makeDefault = useMutation({
    mutationFn: (id: number) => opportunityService.setDefaultProfile(id),
    onSuccess: () => {
      toast.success("Default profile updated");
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => opportunityService.deleteProfile(id),
    onSuccess: () => {
      toast.success("Profile deleted");
      setSelectedId(null);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (error) => toast.error(error.message),
  });

  const selected = list.find((p) => p.id === selectedId) ?? null;

  const handleNewProfile = () => {
    setCreatingNew(true);
    setSelectedId(null);
  };

  const handleSelectProfile = (id: number | null) => {
    if (id !== null) setSelectedId(id);
    setCreatingNew(false);
  };

  const handleCreated = (id: number) => {
    setSelectedId(id);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>User Profiles</CardTitle>
        <p className="text-sm text-muted-foreground">Keep separate profiles/resumes for different roles. The default profile is used for scoring and tailoring unless you pick another.</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {list.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => handleSelectProfile(p.id ?? null)}
              className={`rounded-full border px-3 py-1.5 text-sm transition ${p.id === selectedId && !creatingNew ? "glass-subtle border-primary text-foreground" : "text-muted-foreground hover:bg-white/30 dark:hover:bg-white/10"}`}
            >
              {p.name || "Untitled"}{p.is_default ? " ★" : ""}
            </button>
          ))}
          <Button variant="outline" size="sm" onClick={handleNewProfile}>+ New profile</Button>
        </div>
        {selected || creatingNew ? (
          <div className="flex flex-wrap items-center gap-2 border-b pb-3">
            {selected && !selected.is_default ? (
              <Button variant="outline" size="sm" disabled={makeDefault.isPending} onClick={() => selected.id && makeDefault.mutate(selected.id)}>Set as default</Button>
            ) : selected ? <span className="text-xs text-muted-foreground">This is your default profile.</span> : null}
            {selected && list.length > 1 ? (
              <Button variant="outline" size="sm" disabled={remove.isPending} onClick={() => selected.id && remove.mutate(selected.id)}>Delete</Button>
            ) : null}
          </div>
        ) : null}
        {creatingNew ? (
          <ProfileForm key="new" profile={{}} profileId={null} onCreated={handleCreated} />
        ) : selected ? (
          <ProfileForm key={selected.id} profile={selected} profileId={selected.id ?? null} onCreated={handleCreated} />
        ) : (
          <p className="text-sm text-muted-foreground">Create a profile to get started.</p>
        )}
      </CardContent>
    </Card>
  );
}

function ProfileForm({ profile, profileId, onCreated }: { profile: Profile; profileId: number | null; onCreated?: (id: number) => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<Profile>(profile);
  useEffect(() => setForm(profile), [profile]);
  const save = useMutation({
    mutationFn: () => {
      if (profileId) return opportunityService.updateProfileById(profileId, form);
      return opportunityService.createProfile(form);
    },
    onSuccess: (result: { status: string; id: number } | undefined) => {
      toast.success("Profile saved");
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
      if (!profileId && result?.id) onCreated?.(result.id);
    },
    onError: (error) => toast.error(error.message),
  });
  const upload = useMutation({
    mutationFn: (file: File) => opportunityService.uploadResume(file, profileId ?? undefined),
    onSuccess: (result) => {
      toast.success(`Resume imported (${result.characters.toLocaleString()} characters). Review the fields below, then Save.`);
      qc.invalidateQueries({ queryKey: ["profiles"] });
      qc.invalidateQueries({ queryKey: ["profile"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const update = (key: keyof Profile, value: string) => setForm((current) => ({ ...current, [key]: value }));
  return (
    <div className="grid gap-4 md:grid-cols-2">
        <Input className="md:col-span-2" placeholder="Profile name (e.g. Backend roles)" value={form.name ?? ""} onChange={(e) => update("name", e.target.value)} />
        <div className="md:col-span-2 rounded-lg border border-dashed p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-medium">Import from resume</div>
              <div className="text-xs text-muted-foreground">Upload a PDF, DOCX, or TXT. We extract your details and pre-fill the fields below — nothing is saved until you click Save profile.</div>
              {form.resume_name ? <div className="mt-1 text-xs text-muted-foreground">Current: {form.resume_name}</div> : null}
            </div>
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition hover:bg-white/30 dark:hover:bg-white/10">
              {upload.isPending ? "Importing…" : "Upload resume"}
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                disabled={upload.isPending}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) upload.mutate(file);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
        </div>
        <Input placeholder="Full name" value={form.full_name ?? ""} onChange={(e) => update("full_name", e.target.value)} />
        <Input placeholder="Email" value={form.email ?? ""} onChange={(e) => update("email", e.target.value)} />
        <Input placeholder="Preferred role" value={form.preferred_role ?? form.target_roles ?? ""} onChange={(e) => { update("preferred_role", e.target.value); update("target_roles", e.target.value); }} />
        <Input placeholder="Country" value={form.country ?? ""} onChange={(e) => update("country", e.target.value)} />
        <Input placeholder="Locations" value={form.locations ?? ""} onChange={(e) => update("locations", e.target.value)} />
        <Input placeholder="Remote preference" value={form.remote_preference ?? ""} onChange={(e) => update("remote_preference", e.target.value)} />
        <Input placeholder="Salary expectations" value={form.salary_expectations ?? ""} onChange={(e) => update("salary_expectations", e.target.value)} />
        <Input placeholder="Work authorization" value={form.work_authorization ?? ""} onChange={(e) => update("work_authorization", e.target.value)} />
        <Input placeholder="Years experience" value={form.years_experience ?? ""} onChange={(e) => update("years_experience", e.target.value)} />
        <Input placeholder="Platforms, comma separated" value={form.platforms ?? ""} onChange={(e) => update("platforms", e.target.value)} />
        <Textarea className="md:col-span-2" placeholder="Skills" value={form.skills ?? ""} onChange={(e) => update("skills", e.target.value)} />
        <Textarea className="md:col-span-2" placeholder="Job preferences" value={form.job_preferences ?? ""} onChange={(e) => update("job_preferences", e.target.value)} />
        <Textarea className="md:col-span-2" placeholder="Resume / CV text" value={form.cv_text ?? ""} onChange={(e) => update("cv_text", e.target.value)} />
        <Textarea className="md:col-span-2" placeholder="Deal breakers" value={form.deal_breakers ?? ""} onChange={(e) => update("deal_breakers", e.target.value)} />
        <Button className="md:col-span-2" disabled={save.isPending} onClick={() => save.mutate()}>Save profile</Button>
    </div>
  );
}
