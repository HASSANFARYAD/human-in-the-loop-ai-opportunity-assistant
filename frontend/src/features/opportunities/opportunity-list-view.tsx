"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, Filter, Plus, Search, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";

export function OpportunityListView({ reviewOnly = false }: { reviewOnly?: boolean }) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const pageSize = 12;
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  const scoreMutation = useMutation({
    mutationFn: opportunityService.score,
    onSuccess: () => { toast.success("AI score updated"); qc.invalidateQueries({ queryKey: ["opportunities"] }); },
    onError: (error) => toast.error(error.message),
  });

  const filtered = useMemo(() => {
    return (jobs.data ?? [])
      .filter((item) => !reviewOnly || (item.status ?? "review").includes("review"))
      .filter((item) => status === "all" || (item.status ?? "new") === status)
      .filter((item) => `${item.title} ${item.company} ${item.source}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => Number(b.match_score ?? b.score ?? 0) - Number(a.match_score ?? a.score ?? 0));
  }, [jobs.data, query, reviewOnly, status]);
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{reviewOnly ? "Review Queue" : "All Opportunities"}</h1>
          <p className="text-sm text-muted-foreground">Search, filter, score, and track jobs, hackathons, competitions, webinars, and career opportunities.</p>
        </div>
        <Button asChild><Link href="/opportunities?import=manual"><Plus className="h-4 w-4" /> Manual import</Link></Button>
      </div>
      <Card>
        <CardContent className="grid gap-3 p-4 md:grid-cols-[1fr_180px_120px]">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder="Search by title, company, source..." />
          </div>
          <select className="h-10 rounded-md border bg-background px-3 text-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="all">All statuses</option>
            <option value="new">New</option>
            <option value="review">Review</option>
            <option value="applied">Applied</option>
            <option value="archived">Archived</option>
          </select>
          <Button variant="outline"><Filter className="h-4 w-4" /> Filters</Button>
        </CardContent>
      </Card>
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">Opportunity</th>
              <th className="p-3">Type</th>
              <th className="p-3">Source</th>
              <th className="p-3">Deadline</th>
              <th className="p-3"><span className="flex items-center gap-1">Score <ArrowUpDown className="h-3 w-3" /></span></th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item) => (
              <tr key={item.id} className="border-t">
                <td className="p-3"><Link href={`/opportunities/${item.id}`} className="font-medium hover:text-primary">{item.title}</Link><div className="text-muted-foreground">{item.company || "Unknown company"} · {item.location || "Remote/unspecified"}</div></td>
                <td className="p-3"><Badge>{item.opportunity_type || "job"}</Badge></td>
                <td className="p-3">{item.source}</td>
                <td className="p-3">{formatDate(item.deadline)}</td>
                <td className={`p-3 font-semibold ${scoreTone(item.match_score ?? item.score)}`}>{Number(item.match_score ?? item.score ?? 0)}</td>
                <td className="p-3"><Badge>{item.status || "new"}</Badge></td>
                <td className="p-3 text-right"><Button size="sm" variant="outline" onClick={() => scoreMutation.mutate(item.id)}><Sparkles className="h-3.5 w-3.5" /> Score</Button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>{filtered.length} results</span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="py-1.5">Page {page} of {pages}</span>
          <Button size="sm" variant="outline" disabled={page === pages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
