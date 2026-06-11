# Introduction

This document defines the product context for the AI opportunity management application using the Next.js frontend backed by the FastAPI service. The review covered the Next.js frontend package and the FastAPI backend package. The application already includes authentication, opportunity listing, manual import, public discovery, provider-based discovery, single-opportunity AI scoring, application material generation, integrations, automation, analytics, audit, and workspace foundations.

## Purpose

The purpose of this requirements document is to convert the requested application context into clear functional, frontend, backend, and acceptance requirements. It identifies what is already present and what must be added or improved in the Next.js application.

## Target Audience

The document is intended for product owners, frontend engineers, backend engineers, QA, and deployment stakeholders who need a shared reference for implementation, parity verification, and acceptance testing.

# Current Verification Summary

The Next.js frontend contains routes for dashboard, opportunities, review queue, automation, AI workspace, analytics, integrations, settings, team, activity, login, register, password reset, and opportunity detail. The backend exposes FastAPI endpoints for auth, profile, jobs, discovery, integrations, providers, automation, feedback, audit logs, reminders, compliance, publishing, workers, health, and workspace-aware resources.

| **Area**                                   | **Verified in Next.js/Backend**                                                                                            | **Gap or Required Action**                                                                                          |
|--------------------------------------------|----------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| System theme                               | Next.js uses next-themes and a topbar toggle for light/dark theme.                                                         | Keep; add persisted system preference and settings-page visibility if required.                                     |
| Recording                                  | No recording workflow was found in the Next.js frontend or backend routes.                                                 | Add recording requirement, storage rules, consent, playback, and transcript handling.                               |
| Print                                      | No explicit print/export action was found.                                                                                 | Add print buttons for opportunity detail, materials, scoring result, and interview preparation.                     |
| User profile                               | Backend has /profile GET and POST. Topbar displays user identity.                                                          | Add full profile page/form in Next.js with resume, skills, roles, locations, preferences, and profile completeness. |
| AI scoring all at once                     | Single-job scoring is implemented through /jobs/{id}/score.                                                                | Add batch scoring endpoint and bulk UI action for selected/all unscored opportunities.                              |
| Selected import from fetched opportunities | Preview table and Import all are implemented.                                                                              | Add checkbox selection and import selected only.                                                                    |
| Interview preparation                      | No dedicated interview-prep module was found.                                                                              | Add job-specific interview questions, prep notes, talking points, and print/export.                                 |
| Resume review and improvement response     | Materials generation includes resume bullets.                                                                              | Add resume review endpoint/UI that evaluates uploaded or stored resume and returns improvement suggestions.         |
| Gmail email open links                     | Gmail ingestion service fetches subject/from/date/body; frontend integration card exists.                                  | Expose Gmail connection/status endpoints and store message URL/thread id so users can open the email in Gmail.      |
| Apply button on jobs                       | Opportunity detail has Open source for item.url.                                                                           | Rename/duplicate as Apply and show in list rows as well as detail page.                                             |
| Multiple public platforms/countries        | Public sources include RemoteJobs.org, Arbeitnow, Remotive, Jobicy, Hacker News, plus RapidAPI LinkedIn and Apify options. | Expand source catalog, country/location filters, source configuration, and per-user country preferences.            |

# Functional Requirements

## Authentication and User Context

Users shall register, log in, remain authenticated through token storage, and see their identity in the workspace header.

Users shall maintain a profile containing resume/CV, skills, target roles, locations, visa/work preferences, salary preferences, and job-source preferences.

Frontend shall call backend profile APIs and show validation/completeness warnings before scoring or materials generation.

## Opportunity Discovery and Import

Users shall manually paste a URL, email text, or job description and preview extracted opportunity data before import.

Users shall fetch public opportunities from selectable sources and filter by role, keywords, location, opportunity type, and work mode.

Users shall select individual preview results or all preview results before import.

Users shall open source/apply URLs directly from opportunity lists and details.

System shall support a configurable source catalog for multiple public platforms and country-specific sources.

## AI Scoring and Materials

Users shall score a single opportunity and view score factors and evaluation JSON in a readable UI.

Users shall score selected or all unscored opportunities in one action, with progress, retry, and failure reporting.

System shall generate tailored application materials grounded in profile/resume and opportunity details.

System shall review the resume and provide prioritized suggestions to improve fit for the selected role.

System shall generate interview preparation content including likely questions, company/role talking points, STAR stories, skill gaps, and suggested answers.

## Gmail and Email Import

Users shall connect Gmail through read-only OAuth.

System shall list matching job alert/recruiter emails without forcing automatic import.

Each imported or previewed email-derived opportunity shall retain an easy Open in Gmail link.

Users shall approve imported opportunities from Gmail message previews.

## Usability, Theme, Print, and Recording

The UI shall support light, dark, and system theme behavior.

Opportunity detail, score reports, materials, resume review, and interview prep shall include print-friendly layouts.

Recording features shall define explicit consent, supported recording target, transcript generation, storage, and deletion requirements before implementation.

# Backend Requirements

| **Capability**   | **Required Endpoint/Service**                           | **Notes**                                                                         |
|------------------|---------------------------------------------------------|-----------------------------------------------------------------------------------|
| Batch scoring    | POST /jobs/score-batch                                  | Accept selected ids or filters; return counts, failures, and updated evaluations. |
| Selective import | POST /discovery/import                                  | Already accepts opportunity array; frontend must pass selected items only.        |
| Resume review    | POST /profile/resume-review or /jobs/{id}/resume-review | Use stored profile/resume and optional job context; save review history.          |
| Interview prep   | POST /jobs/{id}/interview-prep                          | Generate structured prep from job, profile, and evaluation.                       |
| Gmail open links | GET /gmail/messages and import payload mapping          | Include message id, thread id, and web URL compatible with Gmail.                 |
| Apply tracking   | PATCH /jobs/{id}/status                                 | Use status Applied and notes; preserve external apply URL.                        |
| Source catalog   | GET/POST /job-sources                                   | Manage source type, country, auth type, provider, and enabled state.              |

All endpoints must remain user-scoped and workspace-aware where applicable. AI endpoints must fail gracefully when profile data is incomplete and must log provider route, model, prompt version, and errors for auditability.

# Frontend Requirements

| **Screen**         | **Required Updates**                                                                                                    |
|--------------------|-------------------------------------------------------------------------------------------------------------------------|
| Opportunities list | Add Apply link, selected checkbox column, bulk score, bulk import feedback, and source/country filters.                 |
| Opportunity detail | Rename Open source to Apply/Open source, add print, interview prep, resume review, status update, and material editing. |
| Public discovery   | Add checkbox selection for preview results and source catalog with country filters.                                     |
| Integrations       | Add Gmail connect/disconnect/status and message import entry point.                                                     |
| Settings/Profile   | Add editable profile/resume/preferences page instead of only runtime settings text.                                     |
| AI workspace       | Add batch run history, resume review history, interview prep history, and human-readable evaluation display.            |

# Acceptance Criteria

A user can create or update profile/resume data and immediately use it for scoring.

A user can fetch public jobs, select only desired rows, import them, and see imported opportunities.

A user can run AI scoring for one, selected, or all unscored opportunities.

A user can open each job apply/source URL from the list and detail screens.

A user can generate resume feedback and interview preparation for a selected job.

A user can connect Gmail, inspect job-related emails, open the original Gmail message, and import only approved opportunities.

A user can print opportunity details, scoring output, materials, resume review, and interview prep without broken layout.

Theme mode works as light, dark, and system-aware behavior across all app pages.
