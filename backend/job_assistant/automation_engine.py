from __future__ import annotations

from typing import Any, Dict

from job_assistant.db import add_activity_event, add_automation_error, create_automation_run, list_automation_rules, update_automation_run


class AutomationEngine:
    def trigger(self, user_id: int, trigger_event: str, payload: Dict[str, Any] | None = None, workspace_id: int | None = None) -> list[dict[str, Any]]:
        payload = payload or {}
        rules = [rule for rule in list_automation_rules(user_id, workspace_id=workspace_id) if rule.get("trigger_event") == trigger_event]
        results: list[dict[str, Any]] = []
        if not rules:
            run_id = create_automation_run(user_id, trigger_event, payload, status="completed", workspace_id=workspace_id)
            update_automation_run(run_id, user_id, status="completed", output_payload={"message": "No active matching rules."})
            return [{"run_id": run_id, "status": "completed", "message": "No active matching rules."}]
        for rule in rules:
            run_id = create_automation_run(user_id, trigger_event, payload, rule_id=int(rule["id"]), status="running", workspace_id=rule.get("workspace_id") or workspace_id)
            try:
                result = self._execute_rule(user_id, rule, payload)
                update_automation_run(run_id, user_id, status=result.get("status", "completed"), output_payload=result)
                results.append({"run_id": run_id, **result})
            except Exception as exc:
                add_automation_error(user_id, run_id, str(exc), metadata={"rule_id": rule.get("id"), "trigger_event": trigger_event})
                update_automation_run(run_id, user_id, status="failed", error_message=str(exc))
                results.append({"run_id": run_id, "status": "failed", "error": str(exc)})
        return results

    def _execute_rule(self, user_id: int, rule: Dict[str, Any], payload: Dict[str, Any]) -> dict[str, Any]:
        action_type = (rule.get("action_type") or "notify").lower()
        if rule.get("human_approval_required"):
            add_activity_event(user_id, "Automation approval required", f"Rule '{rule.get('name')}' matched {rule.get('trigger_event')}. Review before action.", level="warning", metadata={"rule_id": rule.get("id"), "payload": payload})
            return {"status": "requires_approval", "action_type": action_type, "human_approval_required": True}
        if action_type == "notify":
            message = (rule.get("action_config") or {}).get("message") or f"Automation rule '{rule.get('name')}' triggered."
            add_activity_event(user_id, "Automation notification", message, level="info", metadata={"rule_id": rule.get("id"), "payload": payload})
            return {"status": "completed", "action_type": "notify", "message": message}
        if action_type in ("easy_apply", "linkedin_easy_apply"):
            return self._execute_easy_apply(user_id, rule, payload)
        add_activity_event(user_id, "Automation skipped", f"Unsupported action type: {action_type}", level="warning", metadata={"rule_id": rule.get("id")})
        return {"status": "completed", "action_type": action_type, "message": "Unsupported action skipped safely."}

    def _execute_easy_apply(self, user_id: int, rule: Dict[str, Any], payload: Dict[str, Any]) -> dict[str, Any]:
        import asyncio
        from job_assistant.db import get_integration_settings
        from job_assistant.services.linkedin_easy_apply import easy_apply_for_job

        config = rule.get("action_config") or {}
        browser_settings = get_integration_settings(user_id, "linkedin_browser")
        browser_config = browser_settings.get("config", {}) if browser_settings else {}
        li_at = browser_config.get("li_at", "")
        jsessionid = browser_config.get("jsessionid", "")

        if not li_at:
            add_activity_event(user_id, "Easy Apply failed", "LinkedIn browser cookies not configured.", level="error", metadata={"rule_id": rule.get("id"), "payload": payload})
            return {"status": "failed", "message": "LinkedIn browser cookies not configured"}

        job_urls = payload.get("job_urls", []) or config.get("default_job_urls", [])
        if not job_urls and payload.get("job_url"):
            job_urls = [payload["job_url"]]

        results = []
        for url in job_urls:
            try:
                result = asyncio.run(easy_apply_for_job(
                    user_id, url, li_at=li_at, jsessionid=jsessionid,
                    application_data=payload.get("application_data"),
                    dry_run=config.get("dry_run", True),
                ))
                results.append(result)
            except Exception as exc:
                results.append({"url": url, "status": "error", "reason": str(exc)})

        submitted = [r for r in results if r.get("status") == "submitted"]
        message = f"Easy Apply: {len(submitted)}/{len(results)} submitted"
        add_activity_event(user_id, "Easy Apply completed", message, level="info", metadata={"rule_id": rule.get("id"), "results": results})
        return {"status": "completed", "action_type": "easy_apply", "message": message, "results": results}


automation_engine = AutomationEngine()
