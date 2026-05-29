"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Database, KeyRound, Mail, RefreshCw, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { providerService } from "@/services/provider.service";
import type { Integration, ProviderConfig } from "@/types/api";

const AI_PROVIDERS = [
  ["openai", "OpenAI-compatible"],
  ["azure_openai", "Azure OpenAI"],
  ["grok", "Grok / xAI"],
  ["claude", "Anthropic Claude"],
  ["gemini", "Google Gemini"],
  ["huggingface", "Hugging Face"],
] as const;

const AI_PROVIDER_DEFAULTS: Record<string, Record<string, string>> = {
  openai: { model: "gpt-4o-mini", base_url: "" },
  azure_openai: { model: "gpt-4o-mini", endpoint: "", api_version: "2024-10-21", deployment: "" },
  grok: { model: "grok-3-mini", base_url: "https://api.x.ai/v1" },
  claude: { model: "claude-3-5-sonnet-latest" },
  gemini: { model: "gemini-1.5-pro" },
  huggingface: { model: "mistralai/Mistral-7B-Instruct-v0.3", endpoint: "" },
};

const AI_PROVIDER_MODEL_FALLBACKS: Record<string, string[]> = {
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
  azure_openai: ["gpt-4o-mini", "gpt-4o"],
  grok: ["grok-3-mini", "grok-3", "grok-2-latest"],
  claude: ["claude-3-5-sonnet-latest", "claude-3-5-haiku-latest", "claude-3-opus-latest"],
  gemini: ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
  huggingface: ["mistralai/Mistral-7B-Instruct-v0.3", "meta-llama/Meta-Llama-3-8B-Instruct"],
};

async function fetchAiModels(provider: string, apiKey: string, config: Record<string, string>) {
  if (!apiKey.trim()) throw new Error("Enter the provider API key before fetching models");

  if (provider === "openai" || provider === "grok") {
    const baseUrl = (provider === "grok" ? config.base_url || AI_PROVIDER_DEFAULTS.grok.base_url : config.base_url || "https://api.openai.com/v1").replace(/\/$/, "");
    const response = await fetch(`${baseUrl}/models`, { headers: { Authorization: `Bearer ${apiKey}` } });
    if (!response.ok) throw new Error(`Model fetch failed with ${response.status}`);
    const data = await response.json();
    return ((data.data ?? []) as Array<{ id?: string }>).map((item) => item.id).filter(Boolean) as string[];
  }

  if (provider === "claude") {
    const response = await fetch("https://api.anthropic.com/v1/models", { headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01" } });
    if (!response.ok) throw new Error(`Model fetch failed with ${response.status}`);
    const data = await response.json();
    return ((data.data ?? []) as Array<{ id?: string }>).map((item) => item.id).filter(Boolean) as string[];
  }

  if (provider === "gemini") {
    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${encodeURIComponent(apiKey)}`);
    if (!response.ok) throw new Error(`Model fetch failed with ${response.status}`);
    const data = await response.json();
    return ((data.models ?? []) as Array<{ name?: string; supportedGenerationMethods?: string[] }>)
      .filter((item) => item.supportedGenerationMethods?.includes("generateContent"))
      .map((item) => item.name?.replace("models/", ""))
      .filter(Boolean) as string[];
  }

  if (provider === "azure_openai") {
    const endpoint = (config.endpoint || "").replace(/\/$/, "");
    const apiVersion = config.api_version || AI_PROVIDER_DEFAULTS.azure_openai.api_version;
    if (!endpoint) throw new Error("Enter the Azure endpoint before fetching deployments");
    const response = await fetch(`${endpoint}/openai/deployments?api-version=${encodeURIComponent(apiVersion)}`, { headers: { "api-key": apiKey } });
    if (!response.ok) throw new Error(`Deployment fetch failed with ${response.status}`);
    const data = await response.json();
    return ((data.data ?? []) as Array<{ id?: string; model?: string }>).map((item) => item.id || item.model).filter(Boolean) as string[];
  }

  return AI_PROVIDER_MODEL_FALLBACKS[provider] ?? [];
}

const SERVICES = [
  { service: "ai_provider", label: "AI Provider", icon: Bot, description: "Model, provider, base URL, Azure deployment, and provider API key." },
  { service: "gmail", label: "Gmail", icon: Mail, description: "Gmail OAuth is handled by the backend OAuth flow; configure Google credentials in backend env." },
  { service: "linkedin", label: "LinkedIn Posting", icon: KeyRound, description: "Official LinkedIn post API token, author URN, and API version." },
  { service: "rapidapi_linkedin", label: "RapidAPI LinkedIn Jobs", icon: KeyRound, description: "RapidAPI LinkedIn jobs host, endpoint, and default automated search filters." },
  { service: "apify", label: "Apify Scraping", icon: Database, description: "Apify token, actor id, and input JSON template." },
] as const;

const RAPIDAPI_LINKEDIN_HOST = "linkedin-data-api.p.rapidapi.com";
const RAPIDAPI_LINKEDIN_ENDPOINT = "https://linkedin-data-api.p.rapidapi.com/search-jobs";

function getIntegration(integrations: Integration[] | undefined, service: string) {
  return (integrations ?? []).find((item) => item.service === service);
}

function useIntegrationForm(selected: Integration | undefined) {
  const [apiKey, setApiKey] = useState("");
  const [config, setConfig] = useState<Record<string, string>>({});
  const selectedConfig = useMemo(() => selected?.config ?? {}, [selected]);

  useEffect(() => {
    setApiKey("");
    setConfig(Object.fromEntries(Object.entries(selectedConfig).map(([key, value]) => [key, String(value ?? "")])));
  }, [selectedConfig]);

  return { apiKey, setApiKey, config, setConfig };
}

export function IntegrationsView() {
  const searchParams = useSearchParams();
  const selectedService = searchParams.get("service") ?? "ai_provider";
  const tab = searchParams.get("tab");
  const qc = useQueryClient();
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: () => providerService.integrations() });
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => providerService.providers() });
  const providerHealth = useQuery({ queryKey: ["provider-health"], queryFn: () => providerService.health() });

  if (tab === "providers") {
    return <ProviderRegistry providers={providers.data ?? []} providerHealth={providerHealth.data ?? {}} />;
  }

  const service = SERVICES.find((item) => item.service === selectedService) ?? SERVICES[0];
  const selected = getIntegration(integrations.data, service.service);
  const form = useIntegrationForm(selected);
  const save = useMutation({
    mutationFn: (payload: { apiKey: string; config: Record<string, unknown> }) =>
      providerService.saveIntegration(service.service, {
        api_key: payload.apiKey,
        config: payload.config,
        keep_existing_api_key_if_blank: true,
      }),
    onSuccess: () => {
      toast.success(`${service.label} settings saved`);
      qc.invalidateQueries({ queryKey: ["integrations"] });
      qc.invalidateQueries({ queryKey: ["provider-health"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: () => providerService.deleteIntegration(service.service),
    onSuccess: () => {
      toast.success(`${service.label} settings removed`);
      qc.invalidateQueries({ queryKey: ["integrations"] });
      qc.invalidateQueries({ queryKey: ["provider-health"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Integrations</h1>
        <p className="text-sm text-muted-foreground">These forms mirror the working Streamlit integration flows and save to the same FastAPI contracts.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {SERVICES.map((item) => {
          const Icon = item.icon;
          const configured = getIntegration(integrations.data, item.service)?.has_api_key;
          return (
            <Link key={item.service} href={`/integrations?service=${item.service}`}>
              <Card className="h-full transition hover:border-primary/60 hover:shadow-soft">
                <CardContent className="p-5">
                  <Icon className="mb-4 h-5 w-5 text-primary" />
                  <div className="font-medium">{item.label}</div>
                  <Badge className="mt-3">{configured ? "configured" : "not configured"}</Badge>
                  <p className="mt-3 text-xs text-muted-foreground">{item.description}</p>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{service.label}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <ServiceForm service={service.service} selected={selected} form={form} onSave={(config) => save.mutate({ apiKey: form.apiKey, config })} saving={save.isPending} />
          <div className="flex flex-wrap items-center gap-3 border-t pt-4">
            <Badge>{selected?.has_api_key ? "stored key present" : "no stored key"}</Badge>
            <Button variant="destructive" disabled={!selected || remove.isPending} onClick={() => remove.mutate()}>
              <Trash2 className="h-4 w-4" /> Remove settings
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Saved Configuration</CardTitle></CardHeader>
        <CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(selected ?? { service: service.service, has_api_key: false, config: {} }, null, 2)}</pre></CardContent>
      </Card>
    </div>
  );
}

type IntegrationFormState = ReturnType<typeof useIntegrationForm>;

function ServiceForm({
  service,
  selected,
  form,
  onSave,
  saving,
}: {
  service: string;
  selected?: Integration;
  form: IntegrationFormState;
  onSave: (config: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const { apiKey, setApiKey, config, setConfig } = form;
  const update = (key: string, value: string) => setConfig((current) => ({ ...current, [key]: value }));

  if (service === "ai_provider") {
    return <AiProviderForm selected={selected} form={form} onSave={onSave} saving={saving} />;
  }

  if (service === "linkedin") {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="LinkedIn OAuth access token"><Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={selected?.has_api_key ? "Leave blank to keep saved token" : "Paste LinkedIn token"} /></Field>
        <Field label="Author URN"><Input value={config.author_urn ?? ""} onChange={(event) => update("author_urn", event.target.value)} placeholder="urn:li:person:... or urn:li:organization:..." /></Field>
        <Field label="LinkedIn API version"><Input value={config.linkedin_version ?? "202604"} onChange={(event) => update("linkedin_version", event.target.value)} /></Field>
        <SaveButton disabled={saving || (!apiKey && !selected?.has_api_key)} onClick={() => onSave({ author_urn: config.author_urn || "", linkedin_version: config.linkedin_version || "202604" })} />
      </div>
    );
  }

  if (service === "rapidapi_linkedin") {
    return (
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="RapidAPI key"><Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={selected?.has_api_key ? "Leave blank to keep saved key" : "Paste RapidAPI key"} /></Field>
        <Field label="RapidAPI host"><Input value={config.host ?? RAPIDAPI_LINKEDIN_HOST} onChange={(event) => update("host", event.target.value)} /></Field>
        <Field label="Endpoint URL"><Input value={config.endpoint ?? RAPIDAPI_LINKEDIN_ENDPOINT} onChange={(event) => update("endpoint", event.target.value)} /></Field>
        <Field label="Default automated title/search filter"><Input value={config.title_filter ?? ""} onChange={(event) => update("title_filter", event.target.value)} placeholder="Software Engineer OR Data Analyst" /></Field>
        <Field label="Default automated location filter"><Input value={config.location_filter ?? "Remote"} onChange={(event) => update("location_filter", event.target.value)} /></Field>
        <Field label="Automated API offsets per run"><Input type="number" min={1} max={20} value={config.max_offsets ?? "1"} onChange={(event) => update("max_offsets", event.target.value)} /></Field>
        <SaveButton disabled={saving || (!apiKey && !selected?.has_api_key)} onClick={() => onSave({ host: config.host || RAPIDAPI_LINKEDIN_HOST, endpoint: config.endpoint || RAPIDAPI_LINKEDIN_ENDPOINT, title_filter: config.title_filter || "", location_filter: config.location_filter || "Remote", max_offsets: Number(config.max_offsets || 1) })} />
      </div>
    );
  }

  if (service === "apify") {
    return (
      <div className="grid gap-4">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Apify API token"><Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={selected?.has_api_key ? "Leave blank to keep saved token" : "Paste Apify API token"} /></Field>
          <Field label="Actor id"><Input value={config.actor_id ?? ""} onChange={(event) => update("actor_id", event.target.value)} placeholder="username/actor-name or actor id" /></Field>
        </div>
        <Field label="Input JSON template"><Textarea value={config.input_template ?? '{\n  "startUrls": [{"url": "{{url}}"]}\n}'} onChange={(event) => update("input_template", event.target.value)} /></Field>
        <SaveButton disabled={saving || (!apiKey && !selected?.has_api_key)} onClick={() => {
          try {
            JSON.parse(config.input_template || "{}");
            onSave({ actor_id: config.actor_id || "", input_template: config.input_template || '{\n  "startUrls": [{"url": "{{url}}"]}\n}' });
          } catch (error) {
            toast.error(`Input template is not valid JSON: ${(error as Error).message}`);
          }
        }} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Gmail connection uses the backend OAuth flow from the original app. Configure Google OAuth credentials in backend environment variables, then use the Gmail import workflow once OAuth endpoints are exposed in the API.</p>
      <Badge>{selected?.has_api_key ? "connected" : "not connected"}</Badge>
    </div>
  );
}

function AiProviderForm({
  selected,
  form,
  onSave,
  saving,
}: {
  selected?: Integration;
  form: IntegrationFormState;
  onSave: (config: Record<string, unknown>) => void;
  saving: boolean;
}) {
  const { apiKey, setApiKey, config, setConfig } = form;
  const provider = config.provider || "openai";
  const providerDefaults = AI_PROVIDER_DEFAULTS[provider] ?? AI_PROVIDER_DEFAULTS.openai;
  const [modelOptions, setModelOptions] = useState<string[]>(AI_PROVIDER_MODEL_FALLBACKS[provider] ?? [providerDefaults.model].filter(Boolean));
  const [modelsLoading, setModelsLoading] = useState(false);
  const update = (key: string, value: string) => setConfig((current) => ({ ...current, [key]: value }));
  const modelValue = config.model || providerDefaults.model || "";

  const handleProviderChange = (nextProvider: string) => {
    const defaults = AI_PROVIDER_DEFAULTS[nextProvider] ?? AI_PROVIDER_DEFAULTS.openai;
    setConfig({
      provider: nextProvider,
      model: defaults.model || "",
      base_url: defaults.base_url || "",
      endpoint: defaults.endpoint || "",
      api_version: defaults.api_version || "",
      deployment: defaults.deployment || "",
    });
    setModelOptions(AI_PROVIDER_MODEL_FALLBACKS[nextProvider] ?? [defaults.model].filter(Boolean));
  };

  const saveConfig: Record<string, unknown> = { provider, model: modelValue };
  if (provider === "openai" && config.base_url) saveConfig.base_url = config.base_url;
  if (provider === "grok") saveConfig.base_url = config.base_url || providerDefaults.base_url;
  if (provider === "azure_openai") {
    saveConfig.endpoint = config.endpoint || "";
    saveConfig.api_version = config.api_version || providerDefaults.api_version;
    saveConfig.deployment = config.deployment || "";
  }
  if (provider === "huggingface") saveConfig.endpoint = config.endpoint || "";

  const handleFetchModels = async () => {
    setModelsLoading(true);
    try {
      const models = await fetchAiModels(provider, apiKey, config);
      const nextModels = models.length ? models : AI_PROVIDER_MODEL_FALLBACKS[provider] ?? [];
      setModelOptions(nextModels);
      if (nextModels.length && !nextModels.includes(modelValue)) update("model", nextModels[0]);
      toast.success(models.length ? "Models loaded from provider" : "Using recommended models");
    } catch (error) {
      const fallbackModels = AI_PROVIDER_MODEL_FALLBACKS[provider] ?? [];
      setModelOptions(fallbackModels);
      if (fallbackModels.length && !fallbackModels.includes(modelValue)) update("model", fallbackModels[0]);
      toast.error(`${(error as Error).message}. Showing recommended models.`);
    } finally {
      setModelsLoading(false);
    }
  };

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field label="Provider API key"><Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={selected?.has_api_key ? "Enter key to fetch models, or leave blank to keep saved key" : "Paste provider API key"} /></Field>
      <Field label="Provider"><select className="h-10 rounded-md border bg-background px-3 text-sm" value={provider} onChange={(event) => handleProviderChange(event.target.value)}>{AI_PROVIDERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      {provider === "openai" ? <Field label="Base URL (optional)"><Input value={config.base_url ?? ""} onChange={(event) => update("base_url", event.target.value)} placeholder="Leave blank for OpenAI default" /></Field> : null}
      {provider === "grok" ? <Field label="Base URL"><Input value={config.base_url || providerDefaults.base_url} onChange={(event) => update("base_url", event.target.value)} /></Field> : null}
      {provider === "azure_openai" ? (
        <>
          <Field label="Azure endpoint"><Input value={config.endpoint ?? ""} onChange={(event) => update("endpoint", event.target.value)} placeholder="https://your-resource.openai.azure.com" /></Field>
          <Field label="Azure API version"><Input value={config.api_version || providerDefaults.api_version} onChange={(event) => update("api_version", event.target.value)} /></Field>
          <Field label="Azure deployment name"><Input value={config.deployment ?? ""} onChange={(event) => update("deployment", event.target.value)} placeholder="Your Azure deployment name" /></Field>
        </>
      ) : null}
      {provider === "huggingface" ? <Field label="Endpoint override (optional)"><Input value={config.endpoint ?? ""} onChange={(event) => update("endpoint", event.target.value)} placeholder={`https://api-inference.huggingface.co/models/${modelValue}`} /></Field> : null}
      <div className="grid gap-2 md:col-span-2">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <Field label={provider === "azure_openai" ? "Deployment / model" : "Model"}>
              <select className="h-10 rounded-md border bg-background px-3 text-sm" value={modelValue} onChange={(event) => update("model", event.target.value)}>
                {Array.from(new Set([modelValue, ...modelOptions].filter(Boolean))).map((model) => <option key={model} value={model}>{model}</option>)}
              </select>
            </Field>
          </div>
          <Button variant="outline" disabled={modelsLoading || !apiKey.trim()} onClick={handleFetchModels}>
            <RefreshCw className={modelsLoading ? "h-4 w-4 animate-spin" : "h-4 w-4"} /> Fetch models
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Enter the API key first, then fetch models. If the provider blocks browser model-list calls, recommended models are shown.</p>
      </div>
      <SaveButton disabled={saving || (!apiKey && !selected?.has_api_key)} onClick={() => onSave(saveConfig)} />
    </div>
  );
}

function ProviderRegistry({ providers, providerHealth }: { providers: ProviderConfig[]; providerHealth: Record<string, unknown> }) {
  const qc = useQueryClient();
  const [platform, setPlatform] = useState("ai");
  const [providerName, setProviderName] = useState("openai");
  const [authType, setAuthType] = useState("api_key");
  const [secret, setSecret] = useState("");
  const [priority, setPriority] = useState("100");
  const [isActive, setIsActive] = useState(true);
  const [configJson, setConfigJson] = useState('{\n  "supported_actions": ["health_check"]\n}');
  const save = useMutation({
    mutationFn: () => {
      const parsedConfig = JSON.parse(configJson || "{}");
      const credentialKey = authType === "bearer_token" || authType === "oauth2" ? "access_token" : "api_key";
      return providerService.saveProvider({
        platform,
        provider_name: providerName,
        auth_type: authType,
        credentials: secret.trim() ? { [credentialKey]: secret } : {},
        config: parsedConfig,
        priority: Number(priority || 100),
        is_active: isActive,
        keep_existing_credentials_if_blank: true,
      });
    },
    onSuccess: () => {
      toast.success("Provider registry record saved");
      setSecret("");
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["provider-health"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: (provider: ProviderConfig) => providerService.deleteProvider(provider.platform, provider.provider_name),
    onSuccess: () => {
      toast.success("Provider registry record deleted");
      qc.invalidateQueries({ queryKey: ["providers"] });
      qc.invalidateQueries({ queryKey: ["provider-health"] });
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Provider Registry</h1><p className="text-sm text-muted-foreground">Register user-owned providers by platform, priority, auth type, and encrypted credentials.</p></div>
      <Card><CardHeader><CardTitle>Provider Health</CardTitle></CardHeader><CardContent><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(providerHealth, null, 2)}</pre></CardContent></Card>
      <Card>
        <CardHeader><CardTitle>Add or Update Provider</CardTitle></CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <Field label="Platform"><Input value={platform} onChange={(event) => setPlatform(event.target.value)} placeholder="ai, linkedin, reddit, custom_cms" /></Field>
          <Field label="Provider name"><Input value={providerName} onChange={(event) => setProviderName(event.target.value)} placeholder="openai, rapidapi, apify, custom_proxy" /></Field>
          <Field label="Auth type"><select className="h-10 rounded-md border bg-background px-3 text-sm" value={authType} onChange={(event) => setAuthType(event.target.value)}>{["api_key", "bearer_token", "oauth2", "custom_headers", "webhook_secret", "basic_auth"].map((item) => <option key={item} value={item}>{item}</option>)}</select></Field>
          <Field label="Secret / token / API key"><Input type="password" value={secret} onChange={(event) => setSecret(event.target.value)} placeholder="Leave blank to keep saved credentials" /></Field>
          <Field label="Priority"><Input type="number" min={1} max={1000} value={priority} onChange={(event) => setPriority(event.target.value)} /></Field>
          <label className="flex items-center gap-2 pt-7 text-sm"><input type="checkbox" checked={isActive} onChange={(event) => setIsActive(event.target.checked)} /> Active</label>
          <div className="md:col-span-3"><Field label="Provider config JSON"><Textarea value={configJson} onChange={(event) => setConfigJson(event.target.value)} /></Field></div>
          <Button className="md:col-span-3" disabled={save.isPending} onClick={() => save.mutate()}><Save className="h-4 w-4" /> Save provider registry record</Button>
        </CardContent>
      </Card>
      <Card><CardHeader><CardTitle>Providers</CardTitle></CardHeader><CardContent className="space-y-3">{providers.map((provider) => <div key={`${provider.platform}-${provider.provider_name}`} className="flex items-center justify-between gap-3 rounded-md border p-3"><div><div className="font-medium">{provider.platform} / {provider.provider_name}</div><div className="text-sm text-muted-foreground">{provider.auth_type} · priority {provider.priority ?? 100}</div></div><div className="flex items-center gap-2"><Badge>{provider.is_active ? "active" : "inactive"}</Badge><Button size="sm" variant="destructive" onClick={() => remove.mutate(provider)}><Trash2 className="h-3.5 w-3.5" /> Delete</Button></div></div>)}</CardContent></Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-2 text-sm font-medium">{label}{children}</label>;
}

function SaveButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return <Button className="self-end" disabled={disabled} onClick={onClick}><Save className="h-4 w-4" /> Save settings</Button>;
}
