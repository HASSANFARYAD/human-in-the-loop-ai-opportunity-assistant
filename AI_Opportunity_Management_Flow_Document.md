# Introduction

This document defines the product context for the AI opportunity management application using the Next.js frontend backed by the FastAPI service. The review covered the Next.js frontend package and the FastAPI backend package. The application already includes authentication, opportunity listing, manual import, public discovery, provider-based discovery, single-opportunity AI scoring, application material generation, integrations, automation, analytics, audit, and workspace foundations.

## Purpose

The purpose of this flow document is to define how users and backend services should move through discovery, import, scoring, resume review, interview preparation, application, printing, Gmail handling, and automation workflows.

## Target Audience

The document is intended for product owners, frontend engineers, backend engineers, QA, and deployment stakeholders who need a shared reference for implementation, parity verification, and acceptance testing.

# End-to-End Product Flow

The system flow starts with authentication, profile setup, opportunity discovery/import, review, scoring, materials, application, interview preparation, and ongoing automation. Each step must support both the Next.js frontend user journey and the backend service/API responsibilities.

| **Step** | **User Action**            | **Frontend Responsibility**                                        | **Backend Responsibility**                                            |
|----------|----------------------------|--------------------------------------------------------------------|-----------------------------------------------------------------------|
| 1        | Register or log in         | Collect credentials and store token in auth store.                 | Authenticate, issue token, return public user.                        |
| 2        | Complete profile           | Show editable profile/resume/preferences form.                     | Persist profile and validate completeness.                            |
| 3        | Fetch/import opportunities | Show manual/public/provider/Gmail import options.                  | Extract, scrape, fetch, dedupe, and return preview rows.              |
| 4        | Select preview rows        | Allow individual selection or Import all.                          | Import only selected opportunity payloads.                            |
| 5        | Score fit                  | Run single or batch scoring.                                       | Load profile and job data, call AI scoring service, save evaluations. |
| 6        | Review resume/materials    | Show generated materials and resume improvement feedback.          | Generate grounded materials and resume review output.                 |
| 7        | Prepare interview          | Generate prep pack for selected opportunity.                       | Use job/profile/evaluation to create questions and talking points.    |
| 8        | Apply                      | Open external apply/source URL and optionally set status Applied.  | Persist status and notes.                                             |
| 9        | Print/export               | Provide print-friendly views.                                      | Serve data and optionally save export history.                        |
| 10       | Automate                   | User enables rules for discovery, scoring, reminders, and reviews. | Scheduler/worker executes rules and logs results.                     |

# Opportunity Discovery Flow

User opens Opportunities \> Public Discovery or Manual Import.

User enters role, location, country, keywords, work mode, opportunity type, and selected sources.

Frontend calls the discovery endpoint and displays preview results without saving them.

User reviews title, company, location, type, source, and URL.

User checks selected rows or chooses Import all.

Frontend posts only the approved rows to /discovery/import.

Backend deduplicates by URL/title/company and returns imported/skipped/error counts.

Frontend clears imported previews and refreshes the opportunity list.

Current implementation already supports preview and Import all. The required improvement is row selection, country/source configuration, and clearer imported/skipped feedback per result.

# Gmail Import Flow

User opens Integrations \> Gmail and connects with Google read-only OAuth.

Backend stores encrypted OAuth credentials and returns connection status.

User opens Gmail Import to list recruiter/job alert messages.

Frontend displays subject, sender, date, short body preview, and Open in Gmail link.

User selects one or more emails to extract opportunities.

Backend converts selected email bodies into opportunity previews and includes original Gmail message references.

User approves selected opportunity previews for import.

Imported opportunities retain source Gmail, original sender, and open-message URL.

The backend already contains a Gmail ingestion service and scheduler usage, but the Next.js frontend currently needs direct connection/status/message/import screens and API routes.

# AI Scoring Flow

User confirms profile/resume is complete.

User selects one opportunity or multiple opportunities.

Frontend calls single score or batch score API.

Backend validates profile, loads job records, builds AI prompt from profile and job data, routes through provider abstraction, and saves evaluation.

Frontend shows score, fit summary, strengths, gaps, risks, recommended actions, and run errors.

For batch scoring, frontend shows progress and allows retry of failed items.

The current code supports single-opportunity scoring. All-at-once scoring requires a batch endpoint, run tracking, concurrency/rate-limit handling, and UI controls for selected/all unscored jobs.

# Resume Review and Interview Preparation Flow

| **Flow**              | **Input**                                         | **Output**                                                                                                                        | **Persistence**                                           |
|-----------------------|---------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------|
| Resume review         | Stored resume/profile plus optional selected job. | Improvement response with missing keywords, quantified impact suggestions, ordering changes, and tailored bullet revisions.       | Save review result against profile and optionally job id. |
| Interview preparation | Job detail, profile, evaluation, materials.       | Likely questions, suggested answers, STAR stories, company/role talking points, skill gap plan, and questions to ask interviewer. | Save prep pack against job id.                            |
| Print/export          | Review or prep pack content.                      | Print-friendly report.                                                                                                            | Optional export audit record.                             |

# Apply and Status Flow

User sees an Apply button in the opportunity list and detail page when job.url exists.

Clicking Apply opens the external URL in a new tab.

Frontend prompts or provides an action to mark the job as Applied.

Backend updates job status and notes through the status endpoint.

Dashboard and review queue counts refresh to reflect the new state.

# Error and Edge-Case Flow

If a source blocks scraping, frontend shows the existing supported error message and suggests paste/manual import.

If profile is missing, scoring and generation show a profile-completion prompt instead of a generic failure.

If batch scoring partially fails, successful evaluations are saved and failures are shown with retry actions.

If Gmail OAuth expires, frontend shows reconnect state and prevents message fetch until reconnected.

If apply URL is missing, frontend shows source information and allows manual status update.

If selected discovery results include duplicates, backend returns skipped counts and frontend marks duplicate rows.
