"use client";

import type { TailoredResume, Opportunity } from "@/types/api";

function formatDate() {
  return new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

function parseName(draft: string): string {
  const m = draft.match(/^Name:\s*(.+)/im);
  return m ? m[1].trim() : "";
}

export function CoverLetterPreview({
  resume,
  job,
}: {
  resume: TailoredResume | null;
  job: Opportunity | null;
}) {
  const coverNote = resume?.optional_cover_note ?? "";
  const company = job?.company ?? "Hiring Team";
  const jobTitle = resume?.target_role ?? job?.title ?? "the position";
  const name = resume?.resume_draft ? parseName(resume.resume_draft) : "Your Name";

  return (
    <div className="mx-auto max-w-[210mm] bg-white p-10 font-sans text-gray-800 shadow-sm print:shadow-none">
      <p className="mb-8 text-sm text-gray-500">{formatDate()}</p>
      <div className="mb-6 space-y-1 text-sm text-gray-700">
        <p>Hiring Manager</p>
        <p>{company}</p>
      </div>
      <p className="mb-4 text-sm font-medium text-gray-800">Re: Application for {jobTitle}</p>
      <p className="mb-3 text-sm text-gray-700">Dear Hiring Manager,</p>
      {coverNote ? (
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">{coverNote}</div>
      ) : (
        <div className="space-y-3 text-sm leading-relaxed text-gray-600">
          <p>I am writing to express my strong interest in the {jobTitle} position at {company}.</p>
          <p>My skills and experience align well with the requirements of this role, and I am excited about the opportunity to contribute to your team.</p>
          <p>I have attached my resume for your review and welcome the opportunity to discuss my application further.</p>
        </div>
      )}
      <div className="mt-8 space-y-1 text-sm text-gray-700">
        <p>Sincerely,</p>
        <p className="font-semibold">{name}</p>
      </div>
    </div>
  );
}
