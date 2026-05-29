# Phase 7 — Team and Enterprise Foundation

This phase implements the Milestone 7 foundation for organizations, workspaces, RBAC, shared resources, audit-scope expansion, and an admin summary surface while preserving the current SQLite-first MVP runtime.

## Implemented

### Organizations and workspaces

New tables:

- `organizations`
- `workspaces`
- `workspace_members`

Every active user receives a default personal organization and personal workspace during database initialization or first enterprise bootstrap.

### Role-based access control

New tables:

- `roles`
- `permissions`
- `role_permissions`

Seeded system roles:

- owner
- admin
- manager
- editor
- recruiter
- moderator
- analyst
- contributor
- viewer

Seeded permissions include workspace management, invites, provider management, automation permissions, audit log viewing, AI generation, sharing, publishing, and feedback permissions.

### Shared resources

New table:

- `shared_resources`

Supported shared resource types are intentionally generic so jobs, feedback, posts, workflows, reports, dashboards, documents, and future resources can be shared into workspaces without a schema rewrite.

### Audit expansion

The `audit_logs` table now supports:

- `workspace_id`
- `organization_id`

New audit events are recorded for:

- organization creation
- workspace creation
- workspace member add/update
- shared resource add/update

### API endpoints

New endpoints:

```text
GET/POST /api/v1/enterprise/bootstrap
GET      /api/v1/enterprise/summary
GET      /api/v1/workspaces
POST     /api/v1/organizations
POST     /api/v1/workspaces
GET      /api/v1/workspaces/{workspace_id}/members
POST     /api/v1/workspaces/{workspace_id}/members
GET      /api/v1/roles
GET      /api/v1/permissions
GET      /api/v1/permissions/check
GET      /api/v1/shared-resources
POST     /api/v1/shared-resources
```

### Streamlit UI

A new `Team` page was added with tabs for:

- Workspaces
- Members
- Shared resources
- RBAC
- Admin summary

### Validation

`scripts/smoke_test.py` now verifies:

- default user workspace bootstrap
- organization creation
- workspace creation
- role catalog
- permission catalog
- owner permission check
- resource sharing
- enterprise summary counts

## Limitations

This phase establishes the team/enterprise foundation, not a complete enterprise SaaS layer. The following remain future work:

- email-based pending invitations for users who have not registered yet
- organization-wide policy enforcement across every existing endpoint
- billing management
- enterprise SSO
- granular resource ownership migration for all legacy tables
- full PostgreSQL runtime repository conversion
- organization-wide admin console with cross-user management

## Recommended next step

The next implementation step should connect workspace scope to core resources such as opportunities, feedback, integrations, provider configs, automation rules, and AI generations. This will move the app from user-only data ownership to workspace-aware collaboration.
