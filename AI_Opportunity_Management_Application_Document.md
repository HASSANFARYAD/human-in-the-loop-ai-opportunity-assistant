# Introduction

This document defines the product context for the AI opportunity management application using the Next.js frontend backed by the FastAPI service. The review covered the Next.js frontend package and the FastAPI backend package. The application already includes authentication, opportunity listing, manual import, public discovery, provider-based discovery, single-opportunity AI scoring, application material generation, integrations, automation, analytics, audit, and workspace foundations.

## Purpose

The purpose of this application document is to describe the operating context, major frontend and backend modules, data responsibilities, integration model, and implementation backlog needed to manage the application consistently across the Next.js frontend and FastAPI backend.

## Target Audience

The document is intended for product owners, frontend engineers, backend engineers, QA, and deployment stakeholders who need a shared reference for implementation, parity verification, and acceptance testing.

# Application Context

The application is an AI-assisted opportunity discovery and application-management system. It collects opportunities from manual input, public APIs, provider integrations, and Gmail. It evaluates fit against the user profile/resume, generates application materials, supports review workflows, and tracks automation and audit history.

| **Layer**           | **Current Components**                                                    | **Responsibility**                                                                                                                      |
|---------------------|---------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------|
| Frontend            | Next.js app router, Tailwind CSS, React Query, auth store, services layer | User interface, data fetching, routing, filtering, and action orchestration.                                                            |
| Backend API         | FastAPI router in job_assistant/api.py                                    | Authentication, profile, opportunity CRUD, discovery, scoring, materials, integrations, automation, audit, health, and compliance APIs. |
| AI services         | ai_orchestrator.py, provider registry, generation and scoring services    | Provider routing, job scoring, material generation, prompt versions, and generation history.                                            |
| Data layer          | SQLite data access in db.py with Alembic migration support                | Persistence for users, profiles, jobs, evaluations, materials, integrations, automation, audit, and workspace entities.                 |

# Frontend Application Modules

| **Module**         | **Current State**                                                              | **Required Enhancement**                                                                                          |
|--------------------|--------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| Dashboard          | Shows KPIs, score buckets, source breakdown, and recent opportunities.         | Connect charts to real activity timeline and batch AI scoring summaries.                                          |
| Opportunities      | Lists, filters, scores, imports manually/publicly, and opens detail pages.     | Add apply button, selected import, batch scoring, country/source filters, and status controls.                    |
| Opportunity detail | Shows description, metadata, AI evaluation, materials, notes, and source link. | Add print, apply CTA, editable notes/status persistence, interview prep, resume review, and friendlier AI report. |
| Review queue       | Uses opportunity list in review-only mode.                                     | Add checkbox actions, approve/reject, bulk archive, bulk score, and assignment if team workflow is active.        |
| Integrations       | Manages provider configs and shows Gmail/LinkedIn/Apify options.               | Add explicit Gmail OAuth connection UI and email import workflow.                                                 |
| Settings           | Shows health, audit, usage, feedback, and runtime settings.                    | Split into System Settings and User Profile sections.                                                             |
| AI workspace       | Shows generations, prompt versions, provider health, and activity timeline.    | Add score run history, batch status, resume review, interview prep, and prompt/model traceability.                |

# Backend Application Modules

| **Module**       | **Current State**                                                                       | **Required Enhancement**                                                                            |
|------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Auth/Profile     | Register, login, current user, /profile GET and POST.                                   | Add resume file/text handling, profile completeness checks, and preference schema.                  |
| Jobs             | CRUD, detail, status patch, materials, single scoring.                                  | Add batch score, apply tracking, notes persistence from frontend, and list-level apply URL support. |
| Discovery        | Manual extract, public sources, RapidAPI LinkedIn, Apify, URL import, discovery import. | Add source catalog, selected import UX support, country-specific source metadata, and pagination.   |
| Gmail            | Read-only Gmail ingestion service exists and scheduler uses it.                         | Expose OAuth/status/message APIs to frontend and include open-message links.                        |
| AI orchestration | Provider abstraction, provider health, prompts, ask-json, generations.                  | Add stable schemas for resume review and interview prep plus async/batch execution.                 |
| Automation       | Rules, trigger, runs, errors, worker jobs, scheduler.                                   | Add batch-score automation and Gmail review-before-import rules.                                    |
| Compliance/Admin | Export, deletion request/approval, retention, review.                                   | Apply to Gmail data, recordings/transcripts if recording is implemented.                            |

# Data Model Context

The core entities are User, Profile, Workspace, Opportunity/Job, Evaluation, Materials, Integration Settings, Provider Config, Automation Rule, Automation Run, Audit Log, Feedback, Reminder, and Compliance Export. New entities or fields should be added for source catalog entries, Gmail message references, resume review results, interview preparation outputs, batch score jobs, print/export history, and recording/transcript artifacts if recording becomes in scope.

| **Entity or Field**                 | **Purpose**                                                        |
|-------------------------------------|--------------------------------------------------------------------|
| job.url                             | External source/apply link used by Apply/Open Source actions.      |
| job.status                          | Workflow status such as new, review, applied, archived, interview. |
| job.evaluation/materials            | AI scoring output and generated application materials.             |
| profile.resume_text/resume_file     | Input for scoring, materials, and resume review.                   |
| gmail_message_id/thread_id/open_url | Allows users to return to the original Gmail message.              |
| source.country/source_type/provider | Supports public platform availability by country and provider.     |
| batch_run_id/status/errors          | Tracks all-at-once AI scoring progress and failures.               |

# Implementation Backlog

Add Profile page and API schema alignment for resume, skills, roles, locations, salary, work mode, and country preferences.

Add selected import in DiscoveryPreview with checkbox state and pass selected opportunities to existing import endpoint.

Add batch scoring endpoint, backend worker support, frontend selected/all-unscored action, progress UI, and run history.

Add Apply buttons to opportunity list/detail and status update to Applied when user confirms.

Expose Gmail OAuth/status/message endpoints and add Gmail import UI with Open in Gmail links.

Add resume review endpoint/UI and persist review history.

Add interview preparation endpoint/UI and print-friendly output.

Add print/export buttons and print CSS for key detail/report pages.

Define recording scope and implement only after consent, storage, retention, and transcript requirements are approved.

Expand source catalog and country-aware discovery configuration.
