"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, Database, KeyRound, Mail } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { providerService } from "@/services/provider.service";

const catalog = [
  { service: "openai", label: "OpenAI", icon: Bot },
  { service: "gmail", label: "Gmail", icon: Mail },
  { service: "linkedin", label: "LinkedIn", icon: KeyRound },
  { service: "rapidapi", label: "RapidAPI", icon: KeyRound },
  { service: "apify", label: "Apify", icon: Database },
];

export function IntegrationsView() {
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: () => providerService.integrations() });
  const providers = useQuery({ queryKey: ["providers"], queryFn: () => providerService.providers() });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Integrations</h1><p className="text-sm text-muted-foreground">AI providers, Gmail, LinkedIn, RapidAPI, Apify, and provider registry.</p></div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        {catalog.map((item) => {
          const Icon = item.icon;
          const config = (integrations.data ?? []).find((i) => i.service === item.service);
          return <Card key={item.service}><CardContent className="p-5"><Icon className="mb-4 h-5 w-5 text-primary" /><div className="font-medium">{item.label}</div><Badge className="mt-3">{config?.has_api_key ? "configured" : "not configured"}</Badge></CardContent></Card>;
        })}
      </div>
      <Card><CardHeader><CardTitle>Provider Registry</CardTitle></CardHeader><CardContent className="space-y-3">{(providers.data ?? []).map((provider) => <div key={`${provider.platform}-${provider.provider_name}`} className="flex items-center justify-between rounded-md border p-3"><div><div className="font-medium">{provider.platform} / {provider.provider_name}</div><div className="text-sm text-muted-foreground">Priority {provider.priority ?? 100}</div></div><Badge>{provider.is_active ? "active" : "inactive"}</Badge></div>)}</CardContent></Card>
    </div>
  );
}
