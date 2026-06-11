"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, ExternalLink, Filter, Plus, Search, Sparkles, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DataTable } from "@/components/ui/data-display";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";
import type { Opportunity } from "@/types/api";
import type { ApiError } from "@/services/client";

const PUBLIC_SOURCES = ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"];
const OPPORTUNITY_TYPES = ["auto", "job", "internship", "contract", "freelance", "hackathon", "competition", "grant", "scholarship", "webinar", "event", "other"];
const MANUAL_SOURCES = ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Devpost", "Eventbrite", "Meetup", "Other"];
const WORK_LOCATION_OPTIONS = [
  { value: "all", label: "All" },
  { value: "remote", label: "Remote" },
  { value: "hybrid", label: "Hybrid" },
  { value: "onsite", label: "Office / On-site" },
];
const VALID_OPPORTUNITY_TYPES = new Set(["job", "internship", "contract", "freelance", "competition", "hackathon", "grant", "scholarship"]);

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

export function OpportunityListView({ reviewOnly = false }: { reviewOnly?: boolean }) {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const mode = searchParams.get("import");
  const source = searchParams.get("source");
  const showMaterials = searchParams.get("materials") === "true";
  const showReminders = searchParams.get("reminders") === "true";
  const pageSize = 12;
  const qc = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  const scoreMutation = useMutation({
    mutationFn: opportunityService.score,
    onSuccess: () => { toast.success("AI score updated"); qc.invalidateQueries({ queryKey: ["opportunities"] }); },
    onError: (error) => toast.error(error.message),
  });

  const filtered = useMemo(() => {
    return (jobs.data ?? [])
      .filter((item) => !reviewOnly || (item.status ?? "review").includes("review"))
      .filter((item) => !source || item.source === source)
      .filter((item) => status === "all" || (item.status ?? "new") === status)
      .filter((item) => `${item.title} ${item.company} ${item.source}`.toLowerCase().includes(query.toLowerCase()))
      .sort((a, b) => Number(visibleScore(b) ?? -1) - Number(visibleScore(a) ?? -1));
  }, [jobs.data, query, reviewOnly, source, status]);
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const batchScore = useMutation({
    mutationFn: (job_ids: number[]) => opportunityService.scoreBatch({ job_ids }),
    onSuccess: (data) => {
      toast.success(`Scored ${data.succeeded}/${data.total} selected opportunities${data.skipped ? `; ${data.skipped} skipped` : ""}${data.failed ? `; ${data.failed} failed` : ""}`);
      setSelected([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const toggleSelected = (id: number) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);

  if (mode === "manual") return <ManualImportView />;
  if (source === "public") return <PublicDiscoveryView />;
  if (showMaterials) return <MaterialsView />;
  if (showReminders) return <RemindersView />;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{source === "public" ? "Public Discovery" : reviewOnly ? "Review Queue" : "All Opportunities"}</h1>
          <p className="text-sm text-muted-foreground">Search, filter, score, and track jobs, hackathons, competitions, webinars, and career opportunities.</p>
        </div>
        <Button asChild><Link href="/opportunities?import=manual"><Plus className="h-4 w-4" /> Manual import</Link></Button>
      </div>
      <Card className="no-print">
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
      {selected.length ? (
        <div className="no-print flex flex-wrap items-center gap-2 rounded-lg border bg-muted/40 p-3 text-sm">
          <span>{selected.length} selected</span>
          <Button size="sm" disabled={batchScore.isPending} onClick={() => batchScore.mutate(selected)}>
            <Sparkles className="h-3.5 w-3.5" /> Score selected
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected([])}>Clear</Button>
        </div>
      ) : null}
      <div className="overflow-hidden rounded-lg border">
        <table className="w-full min-w-[860px] text-sm">
          <thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground">
            <tr>
              <th className="p-3">
                <input
                  type="checkbox"
                  aria-label="Select page"
                  checked={pageItems.length > 0 && pageItems.every((item) => selected.includes(item.id))}
                  onChange={(e) => setSelected(e.target.checked ? Array.from(new Set([...selected, ...pageItems.filter(isImportableOpportunity).map((item) => item.id)])) : selected.filter((id) => !pageItems.some((item) => item.id === id)))}
                />
              </th>
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
            {pageItems.map((item) => {
              const importable = isImportableOpportunity(item);
              const scoreValue = visibleScore(item);
              return (
                <tr key={item.id} className="border-t">
                  <td className="p-3"><input type="checkbox" aria-label={`Select ${item.title}`} disabled={!importable} checked={selected.includes(item.id)} onChange={() => toggleSelected(item.id)} /></td>
                  <td className="p-3"><Link href={`/opportunities/${item.id}`} className="font-medium hover:text-primary">{item.title}</Link><div className="text-muted-foreground">{item.company || "Unknown company"} - {item.location || "Remote/unspecified"}</div>{!importable ? <div className="text-xs text-destructive">{item.blocked_reason || item.classification_reason || "Non-opportunity"}</div> : null}</td>
                  <td className="p-3"><Badge>{item.classification || item.opportunity_type || "job"}</Badge></td>
                  <td className="p-3">{item.source}</td>
                  <td className="p-3">{formatDate(item.deadline)}</td>
                  <td className={`p-3 font-semibold ${scoreTone(scoreValue)}`}>{scoreValue == null ? "Skipped" : Number(scoreValue)}</td>
                  <td className="p-3"><Badge>{item.status || "new"}</Badge></td>
                  <td className="p-3 text-right">
                    <div className="flex justify-end gap-2">
                      {item.url && importable ? <Button asChild size="sm" variant="outline"><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" /> Apply</a></Button> : <Button size="sm" variant="outline" disabled>Apply unavailable</Button>}
                      <Button size="sm" variant="outline" disabled={!importable} onClick={() => scoreMutation.mutate(item.id)}><Sparkles className="h-3.5 w-3.5" /> Score</Button>
                    </div>
                  </td>
                </tr>
              );
            })}
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
        toast.success(`Found ${data.opportunities.length} jobs. Review them before importing.`);
        return;
      }
      if (!data.opportunity) {
        setPreview(null);
        setPreviewList([]);
        toast.info(data.warnings?.[0] ?? "No opportunity matched the selected work-location filter.");
        return;
      }
      setPreview(data.opportunity ?? null);
      setPreviewList([]);
      toast.success("Opportunity extracted. Review it before importing.");
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
      toast.success(`Imported ${data.imported ?? data.count} opportunit${(data.imported ?? data.count) === 1 ? "y" : "ies"}${data.skipped_duplicates ? `; skipped ${data.skipped_duplicates} duplicate(s)` : ""}`);
      setRaw("");
      setPreview(null);
      setPreviewList([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Manual Import</h1><p className="text-sm text-muted-foreground">Paste a URL, email, or description from LinkedIn, Indeed, Devpost, Eventbrite, company career pages, or recruiter messages. The backend extracts structured opportunity data first, then you approve import.</p></div>
      <Card><CardContent className="grid gap-4 p-5 md:grid-cols-3">
        <label className="space-y-1.5 text-sm font-medium">
          <span>Source</span>
          <select className="h-10 w-full rounded-md border bg-background/70 px-3 text-sm font-normal" value={source} onChange={(e) => setSource(e.target.value)}>
            {MANUAL_SOURCES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1.5 text-sm font-medium">
          <span>Opportunity type</span>
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
        <Textarea className="md:col-span-2" placeholder="Paste opportunity URL, email, or full description..." value={raw} onChange={(e) => setRaw(e.target.value)} />
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
  const discover = useMutation({
    mutationFn: () => opportunityService.discoverPublic({ query, keywords, location, country, remote_type: remoteType, opportunity_type: opportunityType, sources, limit_per_source: limit }),
    onSuccess: (data) => {
      setResults(data.opportunities);
      toast.success(`Found ${data.opportunities.length} opportunities`);
    },
    onError: (error) => toast.error(error.message),
  });
  const importMutation = useMutation({
    mutationFn: (items: Opportunity[]) => opportunityService.importDiscovered(items),
    onSuccess: (data) => {
      toast.success(`Imported ${data.count} opportunities`);
      setResults([]);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  const toggleSource = (source: string) => setSources((current) => current.includes(source) ? current.filter((item) => item !== source) : [...current, source]);

  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Public Discovery</h1><p className="text-sm text-muted-foreground">Fetch public no-auth sources and filter for jobs, internships, hackathons, competitions, remote/hybrid work, visa terms, and other keywords. LinkedIn/Indeed direct scraping should use RapidAPI or Apify integrations.</p></div>
      <Card><CardContent className="grid gap-4 p-5 md:grid-cols-3">
        <Input placeholder="Search title or role" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Input placeholder="Location or region" value={location} onChange={(e) => setLocation(e.target.value)} />
        <Input placeholder="Keywords: visa hybrid internship..." value={keywords} onChange={(e) => setKeywords(e.target.value)} />
        <Input placeholder="Country preference" value={country} onChange={(e) => setCountry(e.target.value)} />
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={opportunityType} onChange={(e) => setOpportunityType(e.target.value)}>{OPPORTUNITY_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}</select>
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={remoteType} onChange={(e) => setRemoteType(e.target.value)}><option value="all">All work modes</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></select>
        <Input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Number(e.target.value || 20))} />
        <div className="flex flex-wrap gap-2 md:col-span-3">{PUBLIC_SOURCES.map((item) => <button key={item} type="button" className={`rounded-md border px-3 py-1.5 text-sm ${sources.includes(item) ? "glass-subtle text-foreground" : "text-muted-foreground"}`} onClick={() => toggleSource(item)}>{item}</button>)}</div>
        <Button className="md:col-span-3" disabled={!sources.length || discover.isPending} onClick={() => discover.mutate()}><Search className="h-4 w-4" /> Fetch opportunities</Button>
      </CardContent></Card>
      <ProviderDiscoveryPanel />
      <DiscoveryPreview opportunities={results} onImport={(items) => importMutation.mutate(items)} importing={importMutation.isPending} />
    </div>
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
    onSuccess: (data) => { setResults(data.opportunities); toast.success(`RapidAPI returned ${data.opportunities.length} opportunities`); },
    onError: (error) => toast.error(error.message),
  });
  const apify = useMutation({
    mutationFn: () => opportunityService.discoverApify({ url: apifyUrl }),
    onSuccess: (data) => { setResults(data.opportunities); toast.success(`Apify returned ${data.opportunities.length} opportunities`); },
    onError: (error) => toast.error(error.message),
  });
  const importMutation = useMutation({
    mutationFn: (items: Opportunity[]) => opportunityService.importDiscovered(items),
    onSuccess: (data) => { toast.success(`Imported ${data.count} provider results`); setResults([]); qc.invalidateQueries({ queryKey: ["opportunities"] }); },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card><CardContent className="space-y-5 p-5">
      <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
        <Input placeholder="LinkedIn title filter" value={linkedinTitle} onChange={(e) => setLinkedinTitle(e.target.value)} />
        <Input placeholder="LinkedIn location filter" value={linkedinLocation} onChange={(e) => setLinkedinLocation(e.target.value)} />
        <Button variant="outline" disabled={!linkedinTitle.trim() || rapidapi.isPending} onClick={() => rapidapi.mutate()}><Search className="h-4 w-4" /> Search LinkedIn API</Button>
      </div>
      <div className="grid gap-3 md:grid-cols-[1fr_auto]">
        <Input placeholder="URL for configured Apify actor: LinkedIn, Indeed, Devpost, etc." value={apifyUrl} onChange={(e) => setApifyUrl(e.target.value)} />
        <Button variant="outline" disabled={!apifyUrl.trim() || apify.isPending} onClick={() => apify.mutate()}><Upload className="h-4 w-4" /> Run Apify scraper</Button>
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
      <div className="flex flex-wrap items-center justify-between gap-3"><div className="font-medium">{opportunities.length} preview result(s) - {selectedItems.length} selected - {importableItems.length} importable</div><div className="flex gap-2"><Button variant="outline" disabled={importing || !selectedItems.length} onClick={() => onImport(selectedItems)}><Plus className="h-4 w-4" /> Import selected</Button><Button disabled={importing || !importableItems.length} onClick={() => onImport(importableItems)}><Plus className="h-4 w-4" /> Import importable</Button></div></div>
      <div className="overflow-hidden rounded-lg border"><table className="w-full min-w-[980px] text-sm"><thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground"><tr><th className="p-3"><input type="checkbox" aria-label="Select all previews" checked={selected.length === importableKeys.length && importableKeys.length > 0} onChange={(e) => setSelected(e.target.checked ? importableKeys : [])} /></th><th className="p-3">Title</th><th className="p-3">Classification</th><th className="p-3">Confidence</th><th className="p-3">State</th><th className="p-3">Source</th><th className="p-3">URL</th></tr></thead><tbody>{opportunities.map((item, index) => { const key = keys[index]; const importable = isImportableOpportunity(item); return <tr key={key} className="border-t"><td className="p-3"><input type="checkbox" disabled={!importable} checked={selected.includes(key)} onChange={() => setSelected((current) => current.includes(key) ? current.filter((value) => value !== key) : [...current, key])} /></td><td className="p-3"><div className="font-medium">{item.title}</div><div className="text-muted-foreground">{item.company || ""} {item.location || item.remote_type || ""}</div></td><td className="p-3"><Badge>{item.classification || item.opportunity_type || "unknown"}</Badge></td><td className="p-3">{Math.round(Number(item.opportunity_confidence ?? item.classification_confidence ?? 0) * 100)}%</td><td className="p-3">{importable ? "Importable" : item.blocked_reason || item.classification_reason || "Blocked"}</td><td className="p-3">{item.source}</td><td className="p-3">{item.url && importable ? <a className="text-primary hover:underline" href={item.url} target="_blank" rel="noreferrer">Open</a> : "None"}</td></tr>; })}</tbody></table></div>
    </CardContent></Card>
  );
}

function MaterialsView() {
  const jobs = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list() });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Application Materials</h1><p className="text-sm text-muted-foreground">Open an opportunity to generate and review tailored materials.</p></div>
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
