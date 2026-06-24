"use client";

import type { TailoredResume, Opportunity } from "@/types/api";

function formatDate() {
  return new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
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
  const role = resume?.target_role ?? job?.title ?? "the position";
  const jobTitle = job?.title ?? role;

  return (
    <div className="mx-auto max-w-[210mm] bg-white p-10 text-gray-900 shadow-sm print:shadow-none">
      <p className="mb-8 text-sm text-gray-500">{formatDate()}</p>
      <p className="mb-6 text-sm text-gray-700">Hiring Manager<br />{company}</p>
      <p className="mb-4 text-sm text-gray-700">Re: Application for {jobTitle}</p>
      <p className="mb-2 text-sm text-gray-700">Dear Hiring Manager,</p>
      {coverNote ? (
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-700">{coverNote}</div>
      ) : (
        <div className="space-y-3 text-sm leading-relaxed text-gray-500">
          <p>I am writing to express my strong interest in the {jobTitle} position at {company}.</p>
          <p>My skills and experience align well with the requirements of this role, and I am excited about the opportunity to contribute to your team.</p>
          <p>I have attached my resume for your review and welcome the opportunity to discuss my application further.</p>
        </div>
      )}
      <div className="mt-8 text-sm text-gray-700">
        <p>Sincerely,</p>
        <p className="mt-1 font-semibold">Your Name</p>
      </div>
    </div>
  );
}
