"use client";

import type { TailoredResume, Profile } from "@/types/api";

const sectionTitle = "mb-2 border-b pb-1 text-xs font-bold uppercase tracking-widest text-muted-foreground";

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  if (typeof value === "string") return value.split("\n").filter(Boolean);
  return [];
}

export function ResumePreview({
  resume,
  profile,
}: {
  resume: TailoredResume | null;
  profile?: Profile | null;
}) {
  const summary = resume?.tailored_summary ?? "";
  const bullets = asList(resume?.tailored_experience_bullets);
  const skills = asList(resume?.skills_to_emphasize);
  const keywords = asList(resume?.keywords_to_include);
  const guidance = asList(resume?.application_guidance);
  const name = profile?.full_name ?? "Your Name";
  const email = profile?.email ?? "";
  const targetRole = resume?.target_role ?? profile?.preferred_role ?? "";

  return (
    <div className="mx-auto max-w-[210mm] bg-white text-gray-900 shadow-sm print:shadow-none">
      <div className="flex flex-col sm:flex-row sm:gap-8">
        <div className="bg-slate-50 p-6 sm:w-80 sm:min-w-[220px] print:bg-slate-50">
          <div className="mb-6">
            <h1 className="text-xl font-bold leading-tight text-slate-800">{name}</h1>
            {targetRole ? <p className="mt-1 text-sm font-medium text-slate-500">{targetRole}</p> : null}
            {email ? <p className="mt-1 text-xs text-slate-400">{email}</p> : null}
          </div>
          {skills.length ? (
            <div className="mb-5">
              <h2 className={sectionTitle}>Skills</h2>
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <span key={s} className="rounded-md bg-slate-200 px-2 py-0.5 text-xs font-medium text-slate-700">{s}</span>
                ))}
              </div>
            </div>
          ) : null}
          {keywords.length ? (
            <div className="mb-5">
              <h2 className={sectionTitle}>Keywords</h2>
              <div className="flex flex-wrap gap-1.5">
                {keywords.map((k) => (
                  <span key={k} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{k}</span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="flex-1 p-6">
          {summary ? (
            <div className="mb-6">
              <h2 className={sectionTitle}>Professional Summary</h2>
              <p className="text-sm leading-relaxed text-gray-700">{summary}</p>
            </div>
          ) : null}
          {bullets.length ? (
            <div className="mb-6">
              <h2 className={sectionTitle}>Experience</h2>
              <ul className="space-y-1.5">
                {bullets.map((b, i) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed text-gray-700">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {guidance.length ? (
            <div className="mb-6">
              <h2 className={sectionTitle}>Application Guidance</h2>
              <ul className="space-y-1">
                {guidance.map((g, i) => (
                  <li key={i} className="flex gap-2 text-sm leading-relaxed text-gray-600">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-300" />
                    <span>{g}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {resume?.resume_draft ? (
            <div className="mb-6">
              <h2 className={sectionTitle}>Full Draft</h2>
              <div className="whitespace-pre-wrap rounded-md border bg-slate-50 p-3 font-sans text-sm leading-relaxed text-gray-700">
                {resume.resume_draft}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
