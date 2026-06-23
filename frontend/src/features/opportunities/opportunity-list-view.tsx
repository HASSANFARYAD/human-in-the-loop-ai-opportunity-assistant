"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, ExternalLink, Plus, Search, Sparkles, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DataTable } from "@/components/ui/data-display";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";
import type { BatchScoreResult, Opportunity, OpportunityContentType, ProfileJobDiscoveryResult } from "@/types/api";
import type { ApiError } from "@/services/client";

const PUBLIC_SOURCES = ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"];
const OPPORTUNITY_TYPES = ["auto", "job", "internship", "contract", "freelance"];
const MANUAL_SOURCES = ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Other"];
const WORK_LOCATION_OPTIONS = [
  { value: "all", label: "All" },
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Office / On-site" },
];
const VALID_OPPORTUNITY_TYPES = new Set(["job", "internship", "contract", "freelance"]);
const CONTENT_FILTERS: Array<{ value: OpportunityContentType; label: string }> = [
  { value: "job", label: "Jobs" },
  { value: "internship", label: "Internships" },
  { value: "contract", label: "Contracts" },
  { value: "freelance", label: "Freelance" },
  { value: "all", label: "All saved" },
];

// Mirrors the backend STATUSES list so the status filter actually matches stored values.
const STATUS_FILTERS: Array<{ value: string; label: string }> = [
  { value: "all", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "reviewed", label: "Reviewed" },
  { value: "needs review", label: "Needs review" },
  { value: "applied", label: "Applied" },
  { value: "interview", label: "Interview" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "archived", label: "Archived" },
  { value: "skip", label: "Skip" },
];

function isImportableOpportunity(item: Opportunity) {
  const classification = String(item.classification || item.opportunity_type || "").toLowerCase();
  return item.importable !== false && item.importable !== 0 && VALID_OPPORTUNITY_TYPES.has(classification);
}

function visibleScore(item: Opportunity) {
  return isImportableOpportunity(item) ? item.match_score ?? item.score ?? null : null;
}

function manualImportErrorMessage(error: Error): string {
  const apiError = error as ApiError;
  if (apiError.message) return apiError.message;
  if (apiError.apiStatus === "blocked") {
    return "This source blocked the page fetch. Try another supported URL or paste the job details manually.";
  }
  if (apiError.apiStatus === "invalid_url") return "Invalid URL. Please check the link and try again.";
  if (apiError.apiStatus === "unsupported_source") {
    return "This URL source is not supported. Use a supported job listing URL or paste the job details manually.";
  }
  if (apiError.apiStatus === "url_error") return "The URL could not be fetched. Please check the link and try again.";
  if (apiError.apiStatus === "no_content") return "No usable job content was found at the provided URL.";
  return "Manual import failed. Please check the input and try again.";
}

function bulkScoreErrorMessage(error: Error): string {
  const message = error.message || "";
  const lower = message.toLowerCase();
  if (lower.includes("profile")) return "Add your resume profile before scoring jobs.";
  if (lower.includes("unscored jobs")) return "There are no unscored jobs to score.";
  if (lower.includes("select at least one")) return "Select at least one job to score.";
  if (lower.includes("api key") || lower.includes("provider") || lower.includes("configuration")) {
    return "Configure your AI provider before scoring jobs.";
  }
  return message || "Bulk scoring failed. Please try again.";
}

function batchScoreSummary(data: BatchScoreResult) {
  const scored = data.scored ?? data.succeeded;
  return `Scored ${scored}; skipped ${data.skipped}; failed ${data.failed}.`;
}

function profileDiscoveryErrorMessage(error: Error): string {
  const message = error.message || "";
  const lower = message.toLowerCase();
  if (lower.includes("profile") || lower.includes("resume")) return "Add resume or profile details before finding jobs.";
  if (lower.includes("search terms")) return "No useful search terms were found in your profile.";
  return message || "Could not find jobs from your profile. Please try again.";
}

export function OpportunityListView({ reviewOnly = false }: { reviewOnly?: boolean }) {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [contentType, setContentType] = useState<OpportunityContentType>("job");
  const [page, setPage] = useState(1);
  const mode = searchParams.get("import");
  const source = searchParams.get("source");
  const showMaterials = searchParams.get("materials") === "true";
  const showReminders = searchParams.get("reminders") === "true";
  const pageSize = 12;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [batchResult, setBatchResult] = useState<BatchScoreResult | null>(null);
  const jobs = useQuery({ queryKey: ["opportunities", contentType], queryFn: () => opportunityService.list({ content_type: contentType }) });
  const scoreMutation = useMutation({
    mutationFn: (id: number) => opportunityService.score(id),
    onSuccess: () => { toast.success("AI score updated"); qc.invalidateQueries({ queryKey: ["opportunities"] }); },
    onError: (error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: (jobId: number) => opportunityService.remove(jobId),
    onSuccess: () => {
      toast.success("Job deleted");
      setSelected((current) => current.filter((id) => id !== deleteMutation.variables));
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message || "Failed to delete job"),
  });

  const filtered = useMemo(() => {
    return (jobs.data ?? [])
      .filter((item) => !reviewOnly || (item.status ?? "review").includes("review"))
      .filter((item) => !source || item.source === source)
      .filter((item) => status === "all" || String(item.status ?? "new").toLowerCase() === status)
      .filter((item) => `${item.title} ${item.company} ${item.source}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => Number(visibleScore(b) ?? -1) - Number(visibleScore(a) ?? -1));
  }, [jobs.data, query, reviewOnly, source, status]);
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const unscoredJobCount = useMemo(() => (jobs.data ?? []).filter((item) => isImportableOpportunity(item) && visibleScore(item) == null).length, [jobs.data]);
  const batchScore = useMutation({
    mutationFn: (payload: { job_ids: number[]; score_all_unscored?: boolean }) => opportunityService.scoreBatch(payload),
    onSuccess: (data) => {
      setBatchResult(data);
      toast.success(batchScoreSummary(data));
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(bulkScoreErrorMessage(error)),
  });
  const scoringBusy = batchScore.isPending || scoreMutation.isPending;
  const toggleSelected = (id: number) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  const hasActiveClientFilters = Boolean(query.trim()) || status !== "all";
  const emptyTitle = jobs.isLoading ? "Loading jobs..." : (jobs.data ?? []).length === 0 ? "No jobs saved yet" : "No jobs match these filters";
  const emptyMessage = (jobs.data ?? []).length === 0
    ? "Add a job manually or use Find Jobs to save roles that match your resume."
    : "Try a different search term, status, or job type filter.";

  useEffect(() => {
    setPage(1);
    setSelected([]);
  }, [contentType, query, status]);

  function confirmDelete(jobId: number, title: string) {
    if (window.confirm(`Delete "${title}"? This removes the job and its related tracking data.`)) {
      deleteMutation.mutate(jobId);
    }
  }

  function scoreSelectedJobs() {
    if (!selected.length) {
      toast.error("Select at least one job to score.");
      return;
    }
    setBatchResult(null);
    batchScore.mutate({ job_ids: selected });
  }

  function scoreAllUnscoredJobs() {
    if (!unscoredJobCount) {
      toast.info("There are no unscored jobs to score.");
      return;
    }
    setBatchResult(null);
    batchScore.mutate({ job_ids: [], score_all_unscored: true });
  }

  if (mode === "manual") return <ManualImportView />;
  if (source === "public") return <PublicDiscoveryView />;
  if (showMaterials) return <MaterialsView />;
  if (showReminders) return <RemindersView />;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{source === "public" ? "Find Jobs" : reviewOnly ? "Review Jobs" : "All Jobs"}</h1>
          <p className="text-sm text-muted-foreground">Search, filter, score, and track jobs matched to your resume and preferences.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={scoringBusy || jobs.isLoading || !unscoredJobCount} onClick={scoreAllUnscoredJobs}>
            <Sparkles className="h-4 w-4" /> Score all unscored
          </Button>
          <Button asChild><Link href="/opportunities?import=manual"><Plus className="h-4 w-4" /> Add job</Link></Button>
        </div>
      </div>
      <Card className="no-print">
        <CardContent className="grid gap-3 p-4 md:grid-cols-[1fr_180px_180px]">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder="Search by title, company, source..." />
          </div>
          <select className="h-10 rounded-md border bg-background px-3 text-sm" value={contentType} onChange={(e) => setContentType(e.target.value as OpportunityContentType)} aria-label="Job type filter">
            {CONTENT_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <select className="h-10 rounded-md border bg-background px-3 text-sm" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter">
            {STATUS_FILTERS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </CardContent>
      </Card>
      {selected.length ? (
        <div className="no-print flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
          <span>{selected.length} selected</span>
          <Button size="sm" disabled={scoringBusy} onClick={scoreSelectedJobs}>
            <Sparkles className="h-3.5 w-3.5" /> Score selected jobs
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>Clear</Button>
        </div>
      ) : null}
      {batchResult ? <BatchScoreResultPanel result={batchResult} /> : null}
      {!jobs.isLoading && !pageItems.length ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <BriefcaseEmpty />
            <div>
              <h2 className="text-lg font-semibold">{emptyTitle}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{emptyMessage}</p>
            </div>
            {(jobs.data ?? []).length === 0 && !hasActiveClientFilters ? (
              <div className="flex flex-wrap justify-center gap-2">
                <Button asChild><Link href="/opportunities?source=public">Find jobs</Link></Button>
                <Button asChild variant="outline"><Link href="/opportunities?import=manual">Add job</Link></Button>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : (
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">
                <input
                  type="checkbox"
                  aria-label="Select page"
                  disabled={scoringBusy}
                  checked={pageItems.filter(isImportableOpportunity).length > 0 && pageItems.filter(isImportableOpportunity).every((item) => selected.includes(item.id))}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? Array.from(new Set([...selected, ...pageItems.filter(isImportableOpportunity).map((item) => item.id)]))
                        : selected.filter((id) => !pageItems.filter(isImportableOpportunity).some((item) => item.id === id)),
                    )
                  }
                />
              </th>
              <th className="p-3">Job</th>
              <th className="p-3">Type</th>
              <th className="p-3">Source</th>
              <th className="p-3">Deadline</th>
              <th className="p-3"><span className="flex items-center gap-1">Score <ArrowUpDown className="h-3 w-3" /></span></th>
              <th className="p-3">Status</th>
              <th className="p-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item) => {
              const importable = isImportableOpportunity(item);
              const scoreValue = visibleScore(item);
              return (
                <tr key={item.id} className="border-t">
                  <td className="p-3"><input type="checkbox" aria-label={`Select ${item.title}`} disabled={!importable || scoringBusy} checked={selected.includes(item.id)} onChange={() => toggleSelected(item.id)} /></td>
                  <td className="p-3"><Link href={`/opportunities/${item.id}`} className="font-medium hover:text-primary">{item.title}</Link><div className="text-muted-foreground">{item.company || "Unknown company"} - {item.location || "Remote/unspecified"}</div>{!importable ? <div className="text-xs text-destructive">{item.blocked_reason || item.classification_reason || "Not a job"}</div> : null}</td>
                  <td className="p-3"><Badge>{item.classification || item.opportunity_type || "job"}</Badge></td>
                  <td className="p-3">{item.source}</td>
                  <td className="p-3">{formatDate(item.deadline)}</td>
                  <td className={`p-3 font-semibold ${scoreTone(scoreValue)}`}>{scoreValue == null ? "Skipped" : Number(scoreValue)}</td>
                  <td className="p-3"><Badge>{item.status || "new"}</Badge></td>
                  <td className="p-3 text-right">
                    <div className="flex justify-end gap-2">
                      {item.url && importable ? <Button asChild size="sm" variant="outline"><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" /> Apply</a></Button> : <Button size="sm" variant="outline" disabled>Apply unavailable</Button>}
                      <Button size="sm" variant="outline" disabled={!importable || scoringBusy} onClick={() => scoreMutation.mutate(item.id)}><Sparkles className="h-3.5 w-3.5" /> Score</Button>
                      <Button size="sm" variant="outline" disabled={deleteMutation.isPending} onClick={() => confirmDelete(item.id, item.title)}><Trash2 className="h-3.5 w-3.5" /> Delete</Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      )}
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

function BatchScoreResultPanel({ result }: { result: BatchScoreResult }) {
  const scored = result.scored ?? result.succeeded;
  const issues = result.results.filter((item) => item.status === "skipped" || item.status === "failed").slice(0, 5);
  return (
    <Card className="no-print border-primary/20 bg-primary/5">
      <CardContent className="space-y-3 p-4 text-sm">
        <div className="flex flex-wrap gap-2">
          <Badge>Scored {scored}</Badge>
          <Badge>Skipped {result.skipped}</Badge>
          <Badge className={result.failed ? "border-destructive/40 text-destructive" : undefined}>Failed {result.failed}</Badge>
          {result.using_fallback_scoring ? <Badge>Local fallback used</Badge> : null}
        </div>
        {result.using_fallback_scoring ? (
          <p className="text-muted-foreground">AI provider settings are not configured, so local scoring rules were used for this run.</p>
        ) : null}
        {issues.length ? (
          <div className="space-y-1 text-muted-foreground">
            {issues.map((item) => (
              <div key={`${item.job_id}-${item.status}`}>
                <span className="font-medium text-foreground">{item.title || `Job ${item.job_id}`}:</span> {item.reason || item.error || "Could not score this job."}
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BriefcaseEmpty() {
  return <div className="grid h-12 w-12 place-items-center rounded-md bg-primary/10 text-primary"><Search className="h-5 w-5" /></div>;
}

function ManualImportView() {
  const qc = useQueryClient();
  const [source, setSource] = useState("Manual");
  const [opportunityType, setOpportunityType] = useState("auto");
  const [workLocationFilter, setWorkLocationFilter] = useState("all");
  const [raw, setRaw] = useState("");
  const [preview, setPreview] = useState<Opportunity | null>(null);
  const [previewList, setPreviewList] = useState<Opportunity[]>([]);
  const isListingUrl = /^https?:\/\/\S+/i.test(raw.trim()) && /indeed\.[a-z.]+\/(?:jobs|q-|jobs\/search|jobs\/collections)/i.test(raw.trim());
  const extract = useMutation({
    mutationFn: () => opportunityService.extract({ raw, source, opportunity_type: opportunityType, work_location_filter: workLocationFilter }),
    onSuccess: (data) => {
      if (data.opportunities?.length) {
        setPreview(null);
        setPreviewList(data.opportunities);
        toast.success(`Found ${data.opportunities.length} jobs. Review them before saving.`);
        return;
      }
      if (!data.opportunity) {
        setPreview(null);
        setPreviewList([]);
        toast.info(data.warnings?.[0] ?? "No job matched the selected work-location filter.");
        return;
      }
      setPreview(data.opportunity ?? null);
      setPreviewList([]);
      toast.success("Job extracted. Review it before saving.");
    },
    onError: (error) => toast.error(manualImportErrorMessage(error)),
  });
  const importUrl = useMutation({
    mutationFn: () => opportunityService.importUrl({ url: raw.trim(), source, work_location_filter: workLocationFilter, page_limit: 2 }),
    onSuccess: (data) => {
      toast.success(`Found ${data.jobs_found ?? data.found}; imported ${data.jobs_imported ?? data.imported}; skipped ${data.jobs_skipped_duplicates ?? data.skipped_duplicates} duplicate(s); filtered ${data.jobs_skipped_location_filter ?? 0}`);
      if (data.errors?.length) toast.error(data.errors.join("; "));
      setRaw("");
      setPreview(null);
      setPreviewList([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(manualImportErrorMessage(error)),
  });
  const create = useMutation({
    mutationFn: (items?: Opportunity[]) => opportunityService.importDiscovered(items ?? (preview ? [preview] : [])),
    onSuccess: (data) => {
      toast.success(`Saved ${data.imported ?? data.count} job${(data.imported ?? data.count) === 1 ? "" : "s"}${data.skipped_duplicates ? `; skipped ${data.skipped_duplicates} duplicate(s)` : ""}`);
      setRaw("");
      setPreview(null);
      setPreviewList([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Add Job</h1><p className="text-sm text-muted-foreground">Paste a job URL, email, or description from LinkedIn, Indeed, company career pages, or recruiter messages. Review the extracted job before saving it.</p></div>
      <Card><CardContent className="grid gap-4 p-5 md:grid-cols-3">
        <label className="space-y-1.5 text-sm font-medium">
          <span>Source</span>
          <select className="h-10 w-full rounded-md border bg-background/70 px-3 text-sm font-normal" value={source} onChange={(e) => setSource(e.target.value)}>
            {MANUAL_SOURCES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          <span>Job type</span>
          <select className="h-10 w-full rounded-md border bg-background/70 px-3 text-sm font-normal" value={opportunityType} onChange={(e) => setOpportunityType(e.target.value)}>
            {OPPORTUNITY_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          <span>Work location</span>
          <select className="h-10 w-full rounded-md border bg-background/70 px-3 text-sm font-normal" value={workLocationFilter} onChange={(e) => setWorkLocationFilter(e.target.value)}>
            {WORK_LOCATION_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <Textarea className="md:col-span-2" placeholder="Paste job URL, email, or full description..." value={raw} onChange={(e) => setRaw(e.target.value)} />
        <Button disabled={!raw.trim() || extract.isPending} onClick={() => extract.mutate()}><Sparkles className="h-4 w-4" /> Extract preview</Button>
        <Button variant="secondary" disabled={isListingUrl ? importUrl.isPending : (!preview && !previewList.length) || create.isPending} onClick={() => isListingUrl ? importUrl.mutate() : create.mutate(previewList.length ? previewList : undefined)}><Plus className="h-4 w-4" /> {isListingUrl ? "Import jobs from URL" : "Import approved preview"}</Button>
      </CardContent></Card>
      {preview ? <DiscoveryPreview opportunities={[preview]} onImport={(items) => create.mutate(items)} importing={create.isPending} /> : null}
      {previewList.length ? <DiscoveryPreview opportunities={previewList} onImport={(items) => create.mutate(items)} importing={create.isPending} /> : null}
    </div>
  );
}

function PublicDiscoveryView() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [country, setCountry] = useState("");
  const [remoteType, setRemoteType] = useState("all");
  const [opportunityType, setOpportunityType] = useState("auto");
  const [sources, setSources] = useState<string[]>(PUBLIC_SOURCES);
  const [limit, setLimit] = useState(20);
  const [results, setResults] = useState<Opportunity[]>([]);
  const [profileResult, setProfileResult] = useState<ProfileJobDiscoveryResult | null>(null);
  const discover = useMutation({
    mutationFn: () => opportunityService.discoverPublic({ query, keywords, location, country, remote_type: remoteType, opportunity_type: opportunityType, sources, limit_per_source: limit }),
    onSuccess: (data) => {
      setResults(data.opportunities);
      setProfileResult(null);
      toast.success(`Found ${data.opportunities.length} jobs`);
    },
    onError: (error) => toast.error(error.message),
  });
  const profileDiscover = useMutation({
    mutationFn: () => opportunityService.discoverFromProfile({ sources, limit_per_source: limit, score_results: true }),
    onSuccess: (data) => {
      setResults(data.opportunities);
      setProfileResult(data);
      if (!data.opportunities.length) {
        toast.info(data.message || "No jobs were found from your profile search terms.");
        return;
      }
      toast.success(`Found ${data.opportunities.length} recommended jobs from your profile`);
    },
    onError: (error) => toast.error(profileDiscoveryErrorMessage(error)),
  });
  const importMutation = useMutation({
    mutationFn: (items: Opportunity[]) => opportunityService.importDiscovered(items),
    onSuccess: (data) => {
      toast.success(`Saved ${data.count} jobs`);
      setResults([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const toggleSource = (source: string) => setSources((current) => current.includes(source) ? current.filter((item) => item !== source) : [...current, source]);

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Find Jobs</h1><p className="text-sm text-muted-foreground">Search public job sources and filter by role, location, remote/hybrid work, visa terms, and other keywords.</p></div>
      <Card><CardContent className="grid gap-4 p-5 md:grid-cols-3">
        <Input placeholder="Search title or role" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Input placeholder="Location or region" value={location} onChange={(e) => setLocation(e.target.value)} />
        <Input placeholder="Keywords: visa hybrid internship..." value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <Input placeholder="Country preference" value={country} onChange={(e) => setCountry(e.target.value)} />
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={opportunityType} onChange={(e) => setOpportunityType(e.target.value)}>{OPPORTUNITY_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={remoteType} onChange={(e) => setRemoteType(e.target.value)}><option value="all">All work modes</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select>
        <Input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value || 20))} />
        <div className="flex flex-wrap gap-2 md:col-span-3">{PUBLIC_SOURCES.map((item) => <button key={item} type="button" className={`rounded-md border px-3 py-1.5 text-sm ${sources.includes(item) ? "glass-subtle text-foreground" : "text-muted-foreground"}`} onClick={() => toggleSource(item)}>{item}</button>)}</div>
        <div className="flex flex-wrap gap-2 md:col-span-3">
          <Button disabled={!sources.length || discover.isPending || profileDiscover.isPending} onClick={() => discover.mutate()}><Search className="h-4 w-4" /> Fetch jobs</Button>
          <Button variant="outline" disabled={!sources.length || discover.isPending || profileDiscover.isPending} onClick={() => profileDiscover.mutate()}><Sparkles className="h-4 w-4" /> {profileDiscover.isPending ? "Finding..." : "Find jobs from profile"}</Button>
        </div>
      </CardContent></Card>
      {profileResult ? <ProfileDiscoverySummary result={profileResult} /> : null}
      <ProviderDiscoveryPanel />
      <DiscoveryPreview opportunities={results} onImport={(items) => importMutation.mutate(items)} importing={importMutation.isPending} />
    </div>
  );
}

function ProfileDiscoverySummary({ result }: { result: ProfileJobDiscoveryResult }) {
  return (
    <Card><CardContent className="space-y-3 p-4 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge>Found {result.found}</Badge>
        <Badge>Scored {result.scored}</Badge>
        {result.using_fallback_scoring ? <Badge>Local fallback used</Badge> : null}
      </div>
      <div className="text-muted-foreground">Search terms: {result.query || result.keywords.join(", ")}</div>
      {result.using_fallback_scoring ? <div className="text-muted-foreground">AI provider settings were unavailable, so local scoring rules ranked these jobs.</div> : null}
      {result.warnings?.length ? <div className="text-muted-foreground">{result.warnings.join("; ")}</div> : null}
    </CardContent></Card>
  );
}

function ProviderDiscoveryPanel() {
  const qc = useQueryClient();
  const [linkedinTitle, setLinkedinTitle] = useState("");
  const [linkedinLocation, setLinkedinLocation] = useState("United States OR United Kingdom");
  const [apifyUrl, setApifyUrl] = useState("");
  const [results, setResults] = useState<Opportunity[]>([]);
  const rapidapi = useMutation({
    mutationFn: () => opportunityService.discoverRapidApiLinkedIn({ title_filter: linkedinTitle, location_filter: linkedinLocation, offset: 0 }),
    onSuccess: (data) => { setResults(data.opportunities); toast.success(`RapidAPI returned ${data.opportunities.length} jobs`); },
    onError: (error) => toast.error(error.message),
  });
  const apify = useMutation({
    mutationFn: () => opportunityService.discoverApify({ url: apifyUrl }),
    onSuccess: (data) => { setResults(data.opportunities); toast.success(`Apify returned ${data.opportunities.length} jobs`); },
    onError: (error) => toast.error(error.message),
  });
  const importMutation = useMutation({
    mutationFn: (items: Opportunity[]) => opportunityService.importDiscovered(items),
    onSuccess: (data) => { toast.success(`Saved ${data.count} provider results`); setResults([]); qc.invalidateQueries({ queryKey: ["opportunities"] }); },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card><CardContent className="space-y-5 p-5">
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <Input placeholder="LinkedIn title filter" value={linkedinTitle} onChange={(e) => setLinkedinTitle(e.target.value)} />
        <Input placeholder="LinkedIn location filter" value={linkedinLocation} onChange={(e) => setLinkedinLocation(e.target.value)} />
        <Button variant="outline" disabled={!linkedinTitle.trim() || rapidapi.isPending} onClick={() => rapidapi.mutate()}><Search className="h-4 w-4" /> Search LinkedIn</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <Input placeholder="URL for configured Apify job actor: LinkedIn, Indeed, etc." value={apifyUrl} onChange={(e) => setApifyUrl(e.target.value)} />
        <Button variant="outline" disabled={!apifyUrl.trim() || apify.isPending} onClick={() => apify.mutate()}><Upload className="h-4 w-4" /> Run job scraper</Button>
      </div>
      <DiscoveryPreview opportunities={results} onImport={(items) => importMutation.mutate(items)} importing={importMutation.isPending} />
    </CardContent></Card>
  );
}

function DiscoveryPreview({ opportunities, onImport, importing }: { opportunities: Opportunity[]; onImport: (items: Opportunity[]) => void; importing: boolean }) {
  const [selected, setSelected] = useState<string[]>([]);
  if (!opportunities.length) return null;
  const keys = opportunities.map((item, index) => `${item.url || item.title}-${index}`);
  const importableKeys = keys.filter((_, index) => isImportableOpportunity(opportunities[index]));
  const selectedItems = opportunities.filter((item, index) => selected.includes(keys[index]) && isImportableOpportunity(item));
  const importableItems = opportunities.filter(isImportableOpportunity);
  return (
    <Card><CardContent className="space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div className="font-medium">{opportunities.length} preview result(s) - {selectedItems.length} selected - {importableItems.length} job-like</div><div className="flex gap-2"><Button variant="outline" disabled={importing || !selectedItems.length} onClick={() => onImport(selectedItems)}><Plus className="h-4 w-4" /> Save selected</Button><Button disabled={importing || !importableItems.length} onClick={() => onImport(importableItems)}><Plus className="h-4 w-4" /> Save job-like</Button></div></div>
      <div className="overflow-hidden rounded-lg border"><table className="w-full min-w-[1040px] text-sm"><thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground"><tr><th className="p-3"><input type="checkbox" aria-label="Select all previews" checked={selected.length === importableKeys.length && importableKeys.length > 0} onChange={(e) => setSelected(e.target.checked ? importableKeys : [])} /></th><th className="p-3">Title</th><th className="p-3">Classification</th><th className="p-3">Score</th><th className="p-3">Confidence</th><th className="p-3">State</th><th className="p-3">Source</th><th className="p-3">URL</th></tr></thead><tbody>{opportunities.map((item, index) => { const key = keys[index]; const importable = isImportableOpportunity(item); return <tr key={key} className="border-t"><td className="p-3"><input type="checkbox" disabled={!importable} checked={selected.includes(key)} onChange={() => setSelected((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])} /></td><td className="p-3"><div className="font-medium">{item.title}</div><div className="text-muted-foreground">{item.company || ""} {item.location || item.remote_type || ""}</div></td><td className="p-3"><Badge>{item.classification || item.opportunity_type || "unknown"}</Badge></td><td className={`p-3 font-semibold ${scoreTone(item.match_score ?? item.score ?? null)}`}>{item.match_score ?? item.score ?? "Not scored"}</td><td className="p-3">{Math.round(Number(item.opportunity_confidence ?? item.classification_confidence ?? 0) * 100)}%</td><td className="p-3">{importable ? "Job-like" : item.blocked_reason || item.classification_reason || "Blocked"}</td><td className="p-3">{item.source}</td><td className="p-3">{item.url && importable ? <a className="text-primary hover:underline" href={item.url} target="_blank" rel="noreferrer">Open</a> : "None"}</td></tr>; })}</tbody></table></div>
    </CardContent></Card>
  );
}

function MaterialsView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Application Materials</h1><p className="text-sm text-muted-foreground">Open a job to generate and review tailored materials.</p></div>
      <div className="grid gap-3">{(jobs.data ?? []).map((job) => <Card key={job.id}><CardContent className="flex items-center justify-between p-4"><div><div className="font-medium">{job.title}</div><div className="text-sm text-muted-foreground">{job.company || "Unknown company"}</div></div><Button asChild variant="outline"><Link href={`/opportunities/${job.id}`}>Open materials</Link></Button></CardContent></Card>)}</div>
    </div>
  );
}

function RemindersView() {
  const reminders = useQuery({ queryKey: ["reminders"], queryFn: opportunityService.reminders });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Reminders</h1><p className="text-sm text-muted-foreground">Due reminders returned by the existing reminder API.</p></div>
      <Card><CardContent className="p-5"><DataTable rows={(reminders.data ?? []) as Record<string, unknown>[]} columns={["title", "due_at", "status", "job_id"]} /></CardContent></Card>
    </div>
  );
}
