#!/usr/bin/env python3
"""Local smoke checks for Phase 2 deployment readiness."""
from __future__ import annotations

import json
import os
import tempfile
import sys
from pathlib import Path


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["APP_DB_PATH"] = str(Path(tmp) / "smoke.sqlite3")
        os.environ.setdefault("APP_DATA_DIR", tmp)
        os.environ.setdefault("LOG_DIR", str(Path(tmp) / "logs"))

        from job_assistant.config import settings
        from job_assistant.db import (
            create_feedback,
            db_health,
            get_user_by_email,
            init_db,
            list_feedback,
            list_provider_configs,
            save_provider_config,
            log_ai_generation,
            list_ai_generations,
            upsert_prompt_version,
            list_prompt_versions,
            create_automation_rule,
            list_automation_rules,
            list_automation_runs,

            ensure_user_workspace,
            list_user_workspaces,
            create_organization,
            create_workspace,
            list_roles,
            list_permissions,
            list_role_permissions,
            share_resource,
            list_shared_resources,
            enterprise_summary,
            user_has_permission,
        )
        from job_assistant.provider_registry import provider_registry
        from job_assistant.ai_orchestrator import ai_orchestrator
        from job_assistant.automation_engine import automation_engine
        from job_assistant.runtime import runtime_status, validate_startup_configuration

        init_db()
        health = db_health()
        user = get_user_by_email("local@example.com")
        feedback_id = create_feedback(user["id"], {
            "category": "General Suggestion",
            "title": "Smoke test feedback",
            "description": "Created by scripts/smoke_test.py",
            "severity": "low",
        })
        feedback = list_feedback(user["id"], limit=5)
        save_provider_config(
            user["id"],
            "ai",
            "openai",
            credentials={"api_key": "smoke-test-key"},
            config={"supported_actions": ["draft"]},
            priority=1,
        )
        providers = list_provider_configs(user["id"], platform="ai")
        health_results = provider_registry.health(user["id"], platform="ai")
        fallback_result = provider_registry.execute_with_fallback(user["id"], "ai", "draft", {"source": "smoke"})
        route = ai_orchestrator.resolve_route(user["id"], task_type="smoke")
        log_ai_generation(user["id"], provider=route.provider, model=route.model, task_type="smoke", status="success")
        ai_logs = list_ai_generations(user["id"], limit=5)
        upsert_prompt_version("smoke_prompt", "v1", "Return JSON only", "Smoke test prompt")
        prompt_versions = list_prompt_versions()
        rule_id = create_automation_rule(user["id"], {"name": "Smoke manual rule", "trigger_event": "manual", "action_type": "notify", "action_config": {"message": "Smoke automation"}, "human_approval_required": True})
        automation_results = automation_engine.trigger(user["id"], "manual", {"source": "smoke"})
        automation_runs = list_automation_runs(user["id"], limit=5)
        assert health["status"] == "ok"
        assert feedback_id > 0
        assert any(item["id"] == feedback_id for item in feedback)
        assert providers and providers[0]["has_credentials"] is True
        assert health_results and health_results[0]["status"] == "healthy"
        assert fallback_result.ok is True
        assert route.provider in {"openai", "none"}
        assert ai_logs
        assert prompt_versions
        assert rule_id > 0
        assert automation_results
        assert automation_runs

        workspace = ensure_user_workspace(user["id"])
        workspaces = list_user_workspaces(user["id"])
        org = create_organization(user["id"], "Smoke Test Org")
        ws = create_workspace(user["id"], org["id"], "Smoke Team", "Created by smoke test")
        roles = list_roles()
        permissions = list_permissions()
        role_permissions = list_role_permissions("owner")
        assert user_has_permission(user["id"], ws["id"], "workspace:manage") is True
        shared_id = share_resource(user["id"], ws["id"], "job", "1", "read")
        shared_resources = list_shared_resources(user["id"], workspace_id=ws["id"])
        enterprise = enterprise_summary(user["id"])
        assert workspace["workspace_id"] > 0
        assert workspaces
        assert org["id"] > 0 and ws["id"] > 0
        assert roles and permissions and role_permissions
        assert shared_id > 0 and shared_resources
        assert enterprise["workspaces"] >= 2

        result = {
            "status": "ok",
            "runtime": runtime_status(),
            "warnings": validate_startup_configuration(strict=False),
            "settings_app": settings.app_name,
            "provider_registry": {
                "configured": len(providers),
                "health_status": health_results[0]["status"],
                "fallback_provider": fallback_result.provider_name,
            },
            "ai_orchestration": {"route_provider": route.provider, "logs": len(ai_logs), "prompts": len(prompt_versions)},
            "automation": {"rule_id": rule_id, "runs": len(automation_runs), "last_status": automation_results[0].get("status")},
            "enterprise": enterprise,
        }
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
