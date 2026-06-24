"use client";

import type { TailoredResume, Profile } from "@/types/api";

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.filter(Boolean).map(String);
  if (typeof value === "string") return value.split("\n").filter(Boolean);
  return [];
}

interface ParsedResume {
  name: string;
  email: string;
  phone: string;
  summary: string;
  experience: { company: string; position: string; dates: string; achievements: string[] }[];
  skills: string[];
}

function parseResumeDraft(draft: string): ParsedResume {
  const result: ParsedResume = { name: "", email: "", phone: "", summary: "", experience: [], skills: [] };
  const lines = draft.split("\n");
  let currentSection = "";
  let currentExp: { company: string; position: string; dates: string; achievements: string[] } | null = null;

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    const sectionMatch = line.match(/^(Experience|Skills|Education|Certifications|Projects|Languages):?$/i);
    if (sectionMatch) {
      currentSection = sectionMatch[1].toLowerCase();
      continue;
    }

    if (currentSection === "experience") {
      const companyMatch = line.match(/^Company:\s*(.+)/i);
      const positionMatch = line.match(/^Position:\s*(.+)/i);
      const datesMatch = line.match(/^Dates:\s*(.+)/i);
      const achievementMatch = line.match(/^-\s*(.+)/);

      if (companyMatch) {
        if (currentExp) result.experience.push(currentExp);
        currentExp = { company: companyMatch[1], position: "", dates: "", achievements: [] };
      } else if (positionMatch && currentExp) {
        currentExp.position = positionMatch[1];
      } else if (datesMatch && currentExp) {
        currentExp.dates = datesMatch[1];
      } else if (achievementMatch && currentExp) {
        currentExp.achievements.push(achievementMatch[1]);
      }
      continue;
    }

    const nameMatch = line.match(/^Name:\s*(.+)/i);
    const emailMatch = line.match(/^Email:\s*(.+)/i);
    const phoneMatch = line.match(/^Phone:\s*(.+)/i);
    const summaryMatch = line.match(/^Summary:\s*(.+)/i);

    if (nameMatch) result.name = nameMatch[1];
    else if (emailMatch) result.email = emailMatch[1];
    else if (phoneMatch) result.phone = phoneMatch[1];
    else if (summaryMatch) result.summary = summaryMatch[1];
    else if (currentSection === "skills" && !line.startsWith("Skills")) {
      result.skills.push(line.replace(/^-\s*/, ""));
    }
  }

  if (currentExp) result.experience.push(currentExp);
  return result;
}

export function ResumePreview({
  resume,
  profile,
}: {
  resume: TailoredResume | null;
  profile?: Profile | null;
}) {
  const draftRaw = resume?.resume_draft ?? "";
  const parsed = draftRaw ? parseResumeDraft(draftRaw) : null;

  const name = parsed?.name || profile?.full_name || "Your Name";
  const email = parsed?.email || profile?.email || "";
  const phone = parsed?.phone || "";
  const summary = parsed?.summary || resume?.tailored_summary || "";
  const experience = parsed?.experience || [];
  const skills = parsed?.skills?.length ? parsed.skills : asList(resume?.skills_to_emphasize);
  const bullets = asList(resume?.tailored_experience_bullets);

  return (
    <div className="mx-auto max-w-[210mm] bg-white font-sans text-gray-800 shadow-sm print:shadow-none">
      <div className="border-b-4 border-slate-700 bg-slate-50 px-8 py-7 text-center print:bg-slate-50">
        <h1 className="text-2xl font-bold tracking-tight text-slate-800">{name}</h1>
        <div className="mt-2 flex items-center justify-center gap-3 text-xs text-slate-500">
          {email ? <span>{email}</span> : null}
          {phone ? <span>{phone}</span> : null}
        </div>
      </div>
      <div className="px-8 py-6">
        {summary ? (
          <div className="mb-7">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">Professional Summary</h2>
            <p className="text-sm leading-relaxed text-gray-700">{summary}</p>
          </div>
        ) : null}

        {experience.length ? (
          <div className="mb-7">
            <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-slate-500">Experience</h2>
            <div className="space-y-5">
              {experience.map((exp, i) => (
                <div key={i}>
                  <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:justify-between">
                    <div>
                      <span className="text-sm font-semibold text-gray-800">{exp.position}</span>
                      {exp.company ? <span className="text-sm text-gray-500"> at {exp.company}</span> : null}
                    </div>
                    {exp.dates ? <span className="text-xs text-slate-400">{exp.dates}</span> : null}
                  </div>
                  {exp.achievements.length ? (
                    <ul className="mt-1.5 space-y-1">
                      {exp.achievements.map((a, j) => (
                        <li key={j} className="flex gap-2 text-sm leading-relaxed text-gray-600">
                          <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                          <span>{a}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        ) : bullets.length ? (
          <div className="mb-7">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">Experience</h2>
            <ul className="space-y-1.5">
              {bullets.map((b, i) => (
                <li key={i} className="flex gap-2 text-sm leading-relaxed text-gray-600">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                  <span>{b}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {skills.length ? (
          <div className="mb-7">
            <h2 className="mb-2 text-xs font-bold uppercase tracking-widest text-slate-500">Skills</h2>
            <div className="flex flex-wrap gap-1.5">
              {skills.map((s) => (
                <span key={s} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700">{s}</span>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
