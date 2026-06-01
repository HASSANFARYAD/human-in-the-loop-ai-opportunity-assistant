"use client";

import { useParams } from "next/navigation";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileText, Mic, Printer, Sparkles, Square } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { opportunityService } from "@/services/opportunity.service";
import { formatDate, scoreTone } from "@/lib/utils";
import type { Opportunity } from "@/types/api";

const VALID_OPPORTUNITY_TYPES = new Set(["job", "internship", "contract", "freelance", "competition", "hackathon", "grant", "scholarship"]);

function isImportableOpportunity(item: Opportunity) {
  const classification = String(item.classification || item.opportunity_type || "").toLowerCase();
  return item.importable !== false && item.importable !== 0 && VALID_OPPORTUNITY_TYPES.has(classification);
}

export function OpportunityDetailView() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const qc = useQueryClient();
  const job = useQuery({ queryKey: ["opportunity", id], queryFn: () => opportunityService.detail(id), enabled: Number.isFinite(id) });
  const materials = useQuery({ queryKey: ["materials", id], queryFn: () => opportunityService.materials(id), enabled: Number.isFinite(id) });
  const prepSessions = useQuery({ queryKey: ["interview-prep", id], queryFn: () => opportunityService.interviewPrepSessions(id), enabled: Number.isFinite(id) });
  const resumeReviews = useQuery({ queryKey: ["resume-reviews", id], queryFn: () => opportunityService.resumeReviews(id), enabled: Number.isFinite(id) });
  const recordings = useQuery({ queryKey: ["recordings", id], queryFn: () => opportunityService.recordings(id), enabled: Number.isFinite(id) });
  const score = useMutation({ mutationFn: () => opportunityService.score(id), onSuccess: () => { toast.success("AI evaluation refreshed"); qc.invalidateQueries({ queryKey: ["opportunity", id] }); } });
  const generate = useMutation({ mutationFn: () => opportunityService.generateMaterials(id), onSuccess: () => { toast.success("Materials generated"); qc.invalidateQueries({ queryKey: ["materials", id] }); } });
  const review = useMutation({ mutationFn: () => opportunityService.resumeReview(id), onSuccess: () => { toast.success("Resume review generated"); qc.invalidateQueries({ queryKey: ["resume-reviews", id] }); }, onError: (error) => toast.error(error.message) });
  const prep = useMutation({ mutationFn: () => opportunityService.interviewPrep(id), onSuccess: () => { toast.success("Interview preparation generated"); qc.invalidateQueries({ queryKey: ["interview-prep", id] }); }, onError: (error) => toast.error(error.message) });
  const statusUpdate = useMutation({ mutationFn: (status: string) => opportunityService.updateStatus(id, status, item?.notes ?? ""), onSuccess: () => { toast.success("Status updated"); qc.invalidateQueries({ queryKey: ["opportunity", id] }); } });
  const saveRecording = useMutation({ mutationFn: (payload: { title: string; blob: Blob; duration_ms: number }) => opportunityService.uploadRecording({ ...payload, job_id: id }), onSuccess: () => { toast.success("Recording saved"); qc.invalidateQueries({ queryKey: ["recordings", id] }); }, onError: (error) => toast.error(error.message) });
  const [recording, setRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const startedAtRef = useRef<number>(0);
  const chunksRef = useRef<Blob[]>([]);
  const item = job.data;

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current = [];
      startedAtRef.current = Date.now();
      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => { if (event.data.size) chunksRef.current.push(event.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        saveRecording.mutate({ title: `Practice response for ${item?.title ?? "opportunity"}`, blob, duration_ms: Date.now() - startedAtRef.current });
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

  if (!item) return <div className="text-sm text-muted-foreground">Loading opportunity...</div>;
  const importable = isImportableOpportunity(item);
  const scoreValue = importable ? item.match_score ?? item.score ?? null : null;

  return (
    <div className="print-area grid gap-5 xl:grid-cols-[1fr_360px]">
      <section className="space-y-5">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold">{item.title}</h1>
            <Badge>{item.classification || item.opportunity_type || "job"}</Badge>
            <Badge>{item.status || "new"}</Badge>
          </div>
          <p className="text-muted-foreground">{item.company || "Unknown company"} - {item.location || "Location unspecified"}</p>{!importable ? <p className="mt-2 text-sm text-destructive">{item.blocked_reason || item.classification_reason || "This item is not a valid opportunity."}</p> : null}
        </div>
        <Card><CardHeader><CardTitle>{importable ? "Description" : "Source Snippet"}</CardTitle></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-6">{importable ? (item.description || "No description available.") : (item.raw_source_snippet || item.description || "No source snippet available.")}</p></CardContent></Card>
        <Card><CardHeader><CardTitle>AI Evaluation</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(item.evaluation ?? {}, null, 2)}</pre></CardContent></Card>
        <Card className="print-break-inside-avoid"><CardHeader><CardTitle>Resume Review</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(resumeReviews.data?.[0] ?? {}, null, 2)}</pre></CardContent></Card>
        <Card className="print-break-inside-avoid"><CardHeader><CardTitle>Interview Preparation</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(prepSessions.data?.[0] ?? {}, null, 2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle>Notes</CardTitle></CardHeader><CardContent><Textarea defaultValue={item.notes ?? ""} placeholder="Add private tracking notes..." /></CardContent></Card>
      </section>
      <aside className="space-y-5">
        <Card>
          <CardHeader><CardTitle>Opportunity Metadata</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-muted-foreground">Source</span><span>{item.source}</span></div><div className="flex justify-between"><span className="text-muted-foreground">Classification</span><span>{item.classification || item.opportunity_type || "unknown"}</span></div><div className="flex justify-between"><span className="text-muted-foreground">Confidence</span><span>{Math.round(Number(item.opportunity_confidence ?? item.classification_confidence ?? 0) * 100)}%</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Deadline</span><span>{formatDate(item.deadline)}</span></div>
            <div className="flex justify-between"><span className="text-muted-foreground">Match score</span><span className={`font-semibold ${scoreTone(scoreValue)}`}>{scoreValue == null ? "Skipped" : Number(scoreValue)}</span></div>
            {item.url && importable ? <Button asChild variant="outline" className="w-full"><a href={item.url} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /> Apply</a></Button> : <Button variant="outline" className="w-full" disabled>Apply unavailable</Button>}
            {item.source_email_open_url || item.source_url ? <Button asChild variant="outline" className="w-full"><a href={item.source_email_open_url || item.source_url || ""} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" /> Open original source</a></Button> : null}<Button variant="outline" className="w-full" onClick={() => window.print()}><Printer className="h-4 w-4" /> Print</Button>
            <Button variant="outline" className="w-full" onClick={() => statusUpdate.mutate("Applied")}><ExternalLink className="h-4 w-4" /> Mark applied</Button>
            <Button className="w-full" disabled={!importable} onClick={() => score.mutate()}><Sparkles className="h-4 w-4" /> Refresh AI score</Button>
            <Button className="w-full" variant="secondary" disabled={!importable} onClick={() => generate.mutate()}><FileText className="h-4 w-4" /> Generate materials</Button>
            <Button className="w-full" variant="secondary" disabled={review.isPending} onClick={() => review.mutate()}><FileText className="h-4 w-4" /> {review.isPending ? "Reviewing..." : "Review resume"}</Button>
            <Button className="w-full" variant="secondary" disabled={prep.isPending} onClick={() => prep.mutate()}><Sparkles className="h-4 w-4" /> {prep.isPending ? "Generating..." : "Generate interview prep"}</Button>
            <Button className="w-full" variant={recording ? "destructive" : "outline"} onClick={recording ? stopRecording : startRecording}>{recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />} {recording ? "Stop recording" : "Start practice recording"}</Button>
          </CardContent>
        </Card>
        <Card><CardHeader><CardTitle>Application Materials</CardTitle></CardHeader><CardContent><pre className="max-h-96 overflow-auto rounded-md bg-muted p-4 text-xs">{JSON.stringify(materials.data ?? {}, null, 2)}</pre></CardContent></Card>
        <Card><CardHeader><CardTitle>Recordings</CardTitle></CardHeader><CardContent className="space-y-3">{(recordings.data ?? []).length ? (recordings.data ?? []).map((recording) => <audio key={String(recording.id)} controls className="w-full" src={String(recording.playback_url || recording.data_url)} />) : <div className="text-sm text-muted-foreground">No recordings saved yet.</div>}</CardContent></Card>
        <Card><CardHeader><CardTitle>History</CardTitle></CardHeader><CardContent className="text-sm text-muted-foreground">Created {formatDate(item.created_at)} · Updated {formatDate(item.updated_at)}</CardContent></Card>
      </aside>
    </div>
  );
}
