from __future__ import annotations

from job_assistant.db.core import get_collection

__all__ = [
    "delete_user_data", "delete_all_data",
]


def delete_user_data(user_id: int) -> None:
    job_ids = [int(j["job_id"]) for j in get_collection("jobs").find({"user_id": user_id}, {"job_id": 1})]
    if job_ids:
        jip = {"job_id": {"$in": job_ids}}
        get_collection("reminders").delete_many(jip)
        get_collection("application_materials").delete_many(jip)
        get_collection("evaluations").delete_many(jip)
        get_collection("applications").delete_many(jip)
        get_collection("jobs").delete_many(jip)
    for coll in ["profiles", "integration_settings", "automation_preferences",
                 "activity_events", "feedback", "audit_logs", "ai_generations",
                 "automation_errors", "automation_runs", "automation_rules",
                 "resume_reviews", "interview_prep_sessions", "recordings",
                 "gmail_messages"]:
        get_collection(coll).delete_many({"user_id": user_id})


def delete_all_data(user_id: int = 1) -> None:
    delete_user_data(user_id)
