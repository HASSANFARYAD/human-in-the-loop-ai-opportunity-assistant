"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, Filter, Plus, Search, Sparkles, Upload } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";
import type { Opportunity } from "@/types/api";

const PUBLIC_SOURCES = ["RemoteJobs.org", "Arbeitnow", "Remotive", "Jobicy", "Hacker News Who is hiring"];
const OPPORTUNITY_TYPES = ["auto", "job", "internship", "hackathon", "competition", "webinar", "other"];
const MANUAL_SOURCES = ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Devpost", "Eventbrite", "Meetup", "Other"];

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
      .sort((a, b) => Number(b.match_score ?? b.score ?? 0) - Number(a.match_score ?? a.score ?? 0));
  }, [jobs.data, query, reviewOnly, source, status]);
  const pageItems = filtered.slice((page - 1) * pageSize, page * pageSize);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));

  if (mode === "manual") return <ManualImportView />;
  if (mode === "csv") return <CsvImportView />;
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

function ManualImportView() {
  const qc = useQueryClient();
  const [source, setSource] = useState("Manual");
  const [opportunityType, setOpportunityType] = useState("auto");
  const [raw, setRaw] = useState("");
  const [preview, setPreview] = useState<Opportunity | null>(null);
  const extract = useMutation({
    mutationFn: () => opportunityService.extract({ raw, source, opportunity_type: opportunityType }),
    onSuccess: (data) => {
      setPreview(data.opportunity);
      toast.success("Opportunity extracted. Review it before importing.");
    },
    onError: (error) => toast.error(error.message),
  });
  const create = useMutation({
    mutationFn: () => opportunityService.importDiscovered(preview ? [preview] : []),
    onSuccess: () => {
      toast.success("Opportunity imported");
      setRaw("");
      setPreview(null);
      qc.invalidateQueries({ queryKey: ["opportunities"] });
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">Manual Import</h1><p className="text-sm text-muted-foreground">Paste a URL, email, or description from LinkedIn, Indeed, Devpost, Eventbrite, company career pages, or recruiter messages. The backend extracts structured opportunity data first, then you approve import.</p></div>
      <Card><CardContent className="grid gap-4 p-5 md:grid-cols-2">
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={source} onChange={(e) => setSource(e.target.value)}>
          {MANUAL_SOURCES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <select className="h-10 rounded-md border bg-background/70 px-3 text-sm" value={opportunityType} onChange={(e) => setOpportunityType(e.target.value)}>
          {OPPORTUNITY_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <Textarea className="md:col-span-2" placeholder="Paste opportunity URL, email, or full description..." value={raw} onChange={(e) => setRaw(e.target.value)} />
        <Button disabled={!raw.trim() || extract.isPending} onClick={() => extract.mutate()}><Sparkles className="h-4 w-4" /> Extract preview</Button>
        <Button variant="secondary" disabled={!preview || create.isPending} onClick={() => create.mutate()}><Plus className="h-4 w-4" /> Import approved preview</Button>
      </CardContent></Card>
      {preview ? <DiscoveryPreview opportunities={[preview]} onImport={(items) => create.mutate()} importing={create.isPending} /> : null}
    </div>
  );
}

function PublicDiscoveryView() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [keywords, setKeywords] = useState("");
  const [location, setLocation] = useState("");
  const [remoteType, setRemoteType] = useState("all");
  const [opportunityType, setOpportunityType] = useState("auto");
  const [sources, setSources] = useState<string[]>(PUBLIC_SOURCES);
  const [limit, setLimit] = useState(20);
  const [results, setResults] = useState<Opportunity[]>([]);
  const discover = useMutation({
    mutationFn: () => opportunityService.discoverPublic({ query, keywords, location, remote_type: remoteType, opportunity_type: opportunityType, sources, limit_per_source: limit }),
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
  if (!opportunities.length) return null;
  return (
    <Card><CardContent className="space-y-4 p-5">
      <div className="flex items-center justify-between gap-3"><div className="font-medium">{opportunities.length} preview result(s)</div><Button disabled={importing} onClick={() => onImport(opportunities)}><Plus className="h-4 w-4" /> Import all</Button></div>
      <div className="overflow-hidden rounded-lg border"><table className="w-full min-w-[760px] text-sm"><thead className="bg-muted/60 text-left text-xs uppercase text-muted-foreground"><tr><th className="p-3">Title</th><th className="p-3">Company</th><th className="p-3">Location</th><th className="p-3">Type</th><th className="p-3">Source</th></tr></thead><tbody>{opportunities.map((item, index) => <tr key={`${item.url || item.title}-${index}`} className="border-t"><td className="p-3 font-medium">{item.title}</td><td className="p-3">{item.company || ""}</td><td className="p-3">{item.location || item.remote_type || ""}</td><td className="p-3"><Badge>{item.opportunity_type || "job"}</Badge></td><td className="p-3">{item.source}</td></tr>)}</tbody></table></div>
    </CardContent></Card>
  );
}

function CsvImportView() {
  return (
    <div className="space-y-5">
      <div><h1 className="text-2xl font-semibold">CSV Import</h1><p className="text-sm text-muted-foreground">The backend currently exposes single-opportunity import through `/jobs`; bulk CSV upload needs a backend import endpoint before it can save rows server-side.</p></div>
      <Card><CardContent className="space-y-4 p-5"><Textarea placeholder="title,company,source,description" /><Button disabled>Upload CSV</Button></CardContent></Card>
    </div>
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
      <Card><CardContent className="p-5"><pre className="overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(reminders.data ?? [], null, 2)}</pre></CardContent></Card>
    </div>
  );
}
