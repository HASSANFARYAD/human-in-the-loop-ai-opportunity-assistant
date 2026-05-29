"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";

export function OpportunityDetailView() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["opportunity", id], queryFn: () => opportunityService.detail(id), enabled: Number.isFinite(id) });
  const materials = useQuery({ queryKey: ["materials", id], queryFn: () => opportunityService.materials(id), enabled: Number.isFinite(id) });
  const score = useMutation({ mutationFn: () => opportunityService.score(id), onSuccess: () => { toast.success("AI evaluation refreshed"); qc.invalidateQueries({ queryKey: ["opportunity", id] }); } });
  const generate = useMutation({ mutationFn: () => opportunityService.generateMaterials(id), onSuccess: () => { toast.success("Materials generated"); qc.invalidateQueries({ queryKey: ["materials", id] }); } });
  const item = job.data;

  if (!item) return <div className="text-sm text-muted-foreground">Loading opportunity...</div>;

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
      <section className="space-y-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{item.title}</h1>
            <Badge>{item.opportunity_type || "job"}</Badge>
            <Badge>{item.status || "new"}</Badge>
          </div>
          <p className="text-muted-foreground">{item.company || "Unknown company"} · {item.location || "Location unspecified"}</p>
        </div>
        <Card><CardHeader><CardTitle>Description</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-6">{item.description || "No description available."}</p></CardContent></Card>
        <Card><CardHeader><CardTitle>AI Evaluation</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(item.evaluation ?? {}, null, 2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle>Notes</CardTitle></CardHeader><CardContent><Textarea defaultValue={item.notes ?? ""} placeholder="Add private tracking notes..." /></CardContent></Card>
      </section>
      <aside className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Opportunity Metadata</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Source</span><span>{item.source}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Deadline</span><span>{formatDate(item.deadline)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Match score</span><span className={`font-semibold ${scoreTone(item.match_score ?? item.score)}`}>{Number(item.match_score ?? item.score ?? 0)}</span></div>
            {item.url ? <Button asChild variant="outline" className="w-full"><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /> Open source</a></Button> : null}
            <Button className="w-full" onClick={() => score.mutate()}><Sparkles className="h-4 w-4" /> Refresh AI score</Button>
            <Button className="w-full" variant="secondary" onClick={() => generate.mutate()}><FileText className="h-4 w-4" /> Generate materials</Button>
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle>Application Materials</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(materials.data ?? {}, null, 2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle>History</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">Created {formatDate(item.created_at)} · Updated {formatDate(item.updated_at)}</CardContent></Card>
      </aside>
    </div>
  );
}
