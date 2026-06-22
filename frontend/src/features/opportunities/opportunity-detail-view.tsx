"use client";

import { useParams } from "next/navigation";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Mic, Printer, Sparkles, Square, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { DataFields } from "@/components/ui/data-display";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";
import type { Opportunity, TailoredResume } from "@/types/api";

const VALID_OPPORTUNITY_TYPES = new Set(["job", "internship", "contract", "freelance"]);

function isImportableOpportunity(item: Opportunity) {
  const classification = String(item.classification || item.opportunity_type || "").toLowerCase();
  return item.importable !== false && item.importable !== 0 && VALID_OPPORTUNITY_TYPES.has(classification);
}

function tailorResumeErrorMessage(error: Error): string {
  const message = error.message || "";
  const lower = message.toLowerCase();
  if (lower.includes("profile") || lower.includes("resume")) return message;
  if (lower.includes("description")) return "This job does not have enough description detail to tailor a resume.";
  return message || "Could not tailor the resume. Please try again.";
}

function asList(value: string[] | undefined) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function TailoredResumeCard({ resume }: { resume: TailoredResume | null }) {
  const copyText = [
    resume?.resume_draft,
    resume?.tailored_summary ? `\nTailored Summary\n${resume.tailored_summary}` : "",
    asList(resume?.tailored_experience_bullets).length ? `\nTailored Experience Bullets\n${asList(resume?.tailored_experience_bullets).map((item) => `- ${item}`).join("\n")}` : "",
  ].filter(Boolean).join("\n").trim();

  async function copyResume() {
    if (!copyText) return;
    await navigator.clipboard.writeText(copyText);
    toast.success("Tailored resume copied");
  }

  return (
    <Card className="print-break-inside-avoid">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle>Tailored Resume</CardTitle>
          <Button size="sm" variant="outline" disabled={!copyText} onClick={copyResume}>Copy draft</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {!resume ? <div className="rounded-md border border-dashed p-4 text-muted-foreground">No tailored resume yet. Use Tailor resume to generate a job-specific draft from your saved profile.</div> : null}
        {resume?.using_fallback ? <div className="rounded-md border p-3 text-muted-foreground">AI provider settings were unavailable or failed, so a local tailored draft was generated.</div> : null}
        {resume?.tailored_summary ? <Section title="Tailored summary"><p className="whitespace-pre-wrap leading-6">{resume.tailored_summary}</p></Section> : null}
        {asList(resume?.tailored_experience_bullets).length ? <Section title="Tailored experience bullets"><ul className="list-disc space-y-1 pl-5">{asList(resume?.tailored_experience_bullets).map((item) => <li key={item}>{item}</li>)}</ul></Section> : null}
        {asList(resume?.skills_to_emphasize).length ? <Section title="Skills to emphasize"><p>{asList(resume?.skills_to_emphasize).join(", ")}</p></Section> : null}
        {asList(resume?.keywords_to_include).length ? <Section title="Keywords to include"><p>{asList(resume?.keywords_to_include).join(", ")}</p></Section> : null}
        {resume?.optional_cover_note ? <Section title="Optional cover note"><p className="whitespace-pre-wrap leading-6">{resume.optional_cover_note}</p></Section> : null}
        {asList(resume?.application_guidance).length ? <Section title="Application guidance"><ul className="list-disc space-y-1 pl-5">{asList(resume?.application_guidance).map((item) => <li key={item}>{item}</li>)}</ul></Section> : null}
        {resume?.resume_draft ? <Section title="Copy-ready resume draft"><pre className="whitespace-pre-wrap rounded-md border bg-muted/30 p-3 font-sans leading-6">{resume.resume_draft}</pre></Section> : null}
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-1.5"><h3 className="font-medium">{title}</h3>{children}</section>;
}

export function OpportunityDetailView() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["opportunity", id], queryFn: () => opportunityService.detail(id), enabled: Number.isFinite(id) });
  const materials = useQuery({ queryKey: ["materials", id], queryFn: () => opportunityService.materials(id), enabled: Number.isFinite(id) });
  const prepSessions = useQuery({ queryKey: ["interview-prep", id], queryFn: () => opportunityService.interviewPrepSessions(id), enabled: Number.isFinite(id) });
  const resumeReviews = useQuery({ queryKey: ["resume-reviews", id], queryFn: () => opportunityService.resumeReviews(id), enabled: Number.isFinite(id) });
  const recordings = useQuery({ queryKey: ["recordings", id], queryFn: () => opportunityService.recordings(id), enabled: Number.isFinite(id) });
  const score = useMutation({ mutationFn: () => opportunityService.score(id), onSuccess: () => { toast.success("AI evaluation refreshed"); qc.invalidateQueries({ queryKey: ["opportunity", id] }); qc.invalidateQueries({ queryKey: ["ai-usage"] }); } });
  const scoreFeedback = useMutation({ mutationFn: (signal: "relevant" | "irrelevant") => opportunityService.scoreFeedback(id, signal), onSuccess: () => toast.success("Thanks — I'll use this to calibrate future scoring."), onError: (error) => toast.error(error.message) });
  const generate = useMutation({ mutationFn: () => opportunityService.generateMaterials(id), onSuccess: () => { toast.success("Materials generated"); qc.invalidateQueries({ queryKey: ["materials", id] }); qc.invalidateQueries({ queryKey: ["ai-usage"] }); }, onError: (error) => toast.error(error.message) });
  const tailorResume = useMutation({ mutationFn: () => opportunityService.tailorResume(id), onSuccess: () => { toast.success("Tailored resume generated"); qc.invalidateQueries({ queryKey: ["resume-reviews", id] }); qc.invalidateQueries({ queryKey: ["ai-usage"] }); }, onError: (error) => toast.error(tailorResumeErrorMessage(error)) });
  const prep = useMutation({ mutationFn: () => opportunityService.interviewPrep(id), onSuccess: () => { toast.success("Interview preparation generated"); qc.invalidateQueries({ queryKey: ["interview-prep", id] }); qc.invalidateQueries({ queryKey: ["ai-usage"] }); }, onError: (error) => toast.error(error.message) });
  const saveRecording = useMutation({ mutationFn: (payload: { title: string; blob: Blob; duration_ms: number }) => opportunityService.uploadRecording({ ...payload, job_id: id }), onSuccess: () => { toast.success("Recording saved"); qc.invalidateQueries({ queryKey: ["recordings", id] }); }, onError: (error) => toast.error(error.message) });
  const remove = useMutation({
    mutationFn: () => opportunityService.remove(id),
    onSuccess: () => {
      toast.success("Job deleted");
      qc.invalidateQueries({ queryKey: ["opportunities"] });
      router.replace("/opportunities");
    },
    onError: (error) => toast.error(error.message || "Failed to delete job"),
  });
  const [recording, setRecording] = useState(false);
  const [notes, setNotes] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const startedAtRef = useRef<number>(0);
  const chunksRef = useRef<Blob[]>([]);
  const item = job.data;
  const saveNotes = useMutation({
    mutationFn: () => opportunityService.updateStatus(id, item?.status ?? "new", notes),
    onSuccess: () => {
      toast.success("Notes saved");
      qc.invalidateQueries({ queryKey: ["opportunity", id] });
    },
    onError: (error) => toast.error(error.message),
  });
  const statusUpdate = useMutation({
    mutationFn: (status: string) => opportunityService.updateStatus(id, status, notes),
    onSuccess: () => {
      toast.success("Status updated");
      qc.invalidateQueries({ queryKey: ["opportunity", id] });
    },
    onError: (error) => toast.error(error.message),
  });

  useEffect(() => {
    setNotes(item?.notes ?? "");
  }, [item?.id, item?.notes]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      startedAtRef.current = Date.now();
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        saveRecording.mutate({ title: `Practice response for ${item?.title ?? "job"}`, blob, duration_ms: Date.now() - startedAtRef.current });
        stream.getTracks().forEach((track) => track.stop());
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecording(true);
    } catch {
      toast.error("Microphone permission was denied or recording is unavailable in this browser.");
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    setRecording(false);
  };

  if (!item) return <div className="text-sm text-muted-foreground">Loading job...</div>;
  const importable = isImportableOpportunity(item);
  const scoreValue = importable ? item.match_score ?? item.score ?? null : null;
  const tailoredResume = (resumeReviews.data ?? []).find((entry) => entry.type === "tailored_resume") ?? null;

  function confirmDelete() {
    if (!item) return;
    if (window.confirm(`Delete "${item.title}"? This removes the job and its related tracking data.`)) {
      remove.mutate();
    }
  }

  return (
    <div className="print-area grid gap-5 xl:grid-cols-[1fr_360px]">
      <section className="space-y-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{item.title}</h1>
            <Badge>{item.classification || item.opportunity_type || "job"}</Badge>
            <Badge>{item.status || "new"}</Badge>
          </div>
          <p className="text-muted-foreground">{item.company || "Unknown company"} - {item.location || "Location unspecified"}</p>{!importable ? <p className="mt-2 text-sm text-destructive">{item.blocked_reason || item.classification_reason || "This item is not a valid job."}</p> : null}
        </div>
        <Card><CardHeader><CardTitle>{importable ? "Description" : "Source Snippet"}</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-6">{importable ? (item.description || "No description available.") : (item.raw_source_snippet || item.description || "No source snippet available.")}</p></CardContent></Card>
        <Card><CardHeader><CardTitle>AI Evaluation</CardTitle></CardHeader><CardContent><DataFields data={item.evaluation ?? {}} /></CardContent></Card>
        <TailoredResumeCard resume={tailoredResume} />
        <Card className="print-break-inside-avoid"><CardHeader><CardTitle>Interview Preparation</CardTitle></CardHeader><CardContent><DataFields data={(prepSessions.data?.[0] ?? {}) as Record<string, unknown>} /></CardContent></Card>
        <Card>
          <CardHeader><CardTitle>Notes</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Add private tracking notes..." />
            <div className="flex flex-wrap items-center gap-3">
              <Button disabled={saveNotes.isPending || notes === (item.notes ?? "")} onClick={() => saveNotes.mutate()}>{saveNotes.isPending ? "Saving..." : "Save notes"}</Button>
              {notes !== (item.notes ?? "") ? <span className="text-sm text-muted-foreground">Unsaved changes</span> : <span className="text-sm text-muted-foreground">Notes are saved</span>}
            </div>
          </CardContent>
        </Card>
      </section>
      <aside className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Job Metadata</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Source</span><span>{item.source}</span></div><div className="flex justify-between"><span className="text-muted-foreground">Classification</span><span>{item.classification || item.opportunity_type || "unknown"}</span></div><div className="flex justify-between"><span className="text-muted-foreground">Confidence</span><span>{Math.round(Number(item.opportunity_confidence ?? item.classification_confidence ?? 0) * 100)}%</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Deadline</span><span>{formatDate(item.deadline)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Match score</span><span className={`font-semibold ${scoreTone(scoreValue)}`}>{scoreValue == null ? "Skipped" : Number(scoreValue)}</span></div>
            <div className="flex items-center justify-between"><span className="text-muted-foreground">Is this relevant?</span><span className="flex gap-2"><Button size="icon" variant="outline" className="h-8 w-8" disabled={scoreFeedback.isPending} onClick={() => scoreFeedback.mutate("relevant")} aria-label="Mark relevant"><ThumbsUp className="h-4 w-4" /></Button><Button size="icon" variant="outline" className="h-8 w-8" disabled={scoreFeedback.isPending} onClick={() => scoreFeedback.mutate("irrelevant")} aria-label="Mark irrelevant"><ThumbsDown className="h-4 w-4" /></Button></span></div>
            {item.url && importable ? <Button asChild variant="outline" className="w-full"><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /> Apply</a></Button> : <Button variant="outline" className="w-full" disabled>Apply unavailable</Button>}
            {item.source_email_open_url || item.source_url ? <Button asChild variant="outline" className="w-full"><a href={item.source_email_open_url || item.source_url || ""} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /> Open original source</a></Button> : null}<Button variant="outline" className="w-full" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</Button>
            <Button variant="outline" className="w-full" onClick={() => statusUpdate.mutate("Applied")}><ExternalLink className="h-4 w-4" /> Mark applied</Button>
            <Button className="w-full" disabled={!importable} onClick={() => score.mutate()}><Sparkles className="h-4 w-4" /> Refresh AI score</Button>
            <Button className="w-full" variant="secondary" disabled={!importable} onClick={() => generate.mutate()}><FileText className="h-4 w-4" /> Generate materials</Button>
            <Button className="w-full" variant="secondary" disabled={!importable || tailorResume.isPending} onClick={() => tailorResume.mutate()}><FileText className="h-4 w-4" /> {tailorResume.isPending ? "Tailoring..." : "Tailor resume"}</Button>
            <Button className="w-full" variant="secondary" disabled={prep.isPending} onClick={() => prep.mutate()}><Sparkles className="h-4 w-4" /> {prep.isPending ? "Generating..." : "Generate interview prep"}</Button>
            <Button className="w-full" variant={recording ? "destructive" : "outline"} onClick={recording ? stopRecording : startRecording}>{recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />} {recording ? "Stop recording" : "Start practice recording"}</Button>
            <Button className="w-full" variant="destructive" disabled={remove.isPending} onClick={confirmDelete}><Trash2 className="h-4 w-4" /> {remove.isPending ? "Deleting..." : "Delete job"}</Button>
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle>Application Materials</CardTitle></CardHeader><CardContent><DataFields data={materials.data ?? {}} /></CardContent></Card>
        <Card><CardHeader><CardTitle>Recordings</CardTitle></CardHeader><CardContent className="space-y-3">{(recordings.data ?? []).length ? (recordings.data ?? []).map((recording) => <audio key={String(recording.id)} controls className="w-full" src={String(recording.playback_url || recording.data_url)} />) : <div className="text-sm text-muted-foreground">No recordings saved yet.</div>}</CardContent></Card>
        <Card><CardHeader><CardTitle>History</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">Created {formatDate(item.created_at)} · Updated {formatDate(item.updated_at)}</CardContent></Card>
      </aside>
    </div>
  );
}
