from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from job_assistant.auth import authenticate_user, create_access_token, create_refresh_token, public_user, register_user, revoke_refresh_token, user_from_refresh_token
from job_assistant.db import (
    OPPORTUNITY_TYPES,
    STATUSES,
    create_reminder,
    delete_all_data,
    delete_job,
    due_reminders,
    FEEDBACK_CATEGORIES,
    FEEDBACK_SEVERITIES,
    FEEDBACK_STATUSES,
    create_feedback,
    get_automation_preferences,
    get_evaluation,
    get_integration_settings,
    get_job,
    get_materials,
    get_profile,
    init_db,
    list_activity_events,
    insert_job,
    list_audit_logs,
    create_automation_rule,
    delete_automation_rule,
    list_ai_generations,
    list_automation_errors,
    list_automation_rules,
    list_automation_runs,
    list_prompt_versions,
    update_automation_rule,
    upsert_prompt_version,
    list_feedback,
    list_jobs,
    save_automation_preferences,
    save_evaluation,
    save_integration_settings,
    delete_provider_config,
    list_provider_configs,
    save_provider_config,
    delete_integration_settings,
    save_materials,
    update_feedback_status,
    add_workspace_member,
    create_organization,
    create_workspace,
    enterprise_summary,
    ensure_user_workspace,
    list_permissions,
    list_role_permissions,
    list_roles,
    list_shared_resources,
    list_user_workspaces,
    list_workspace_members,
    share_resource,
    user_has_permission,
    update_status,
    upsert_profile,
)
from job_assistant.config import settings
from job_assistant.crypto import mask_secret
from job_assistant.automation_engine import automation_engine
from job_assistant.services.ai_providers import SUPPORTED_PROVIDERS
from job_assistant.services.apify_integration import apify_items_to_opportunities, build_run_input, run_actor_for_items
from job_assistant.services.generation import generate_materials
from job_assistant.services.gmail_ingest import build_gmail_authorization_url, disconnect_gmail, exchange_gmail_code, fetch_job_alert_messages, get_gmail_connection
from job_assistant.services.linkedin_integration import publish_text_post
from job_assistant.services.rapidapi_linkedin import (
    DEFAULT_ENDPOINT as RAPIDAPI_LINKEDIN_ENDPOINT,
    DEFAULT_HOST as RAPIDAPI_LINKEDIN_HOST,
    rapidapi_items_to_opportunities,
    search_linkedin_jobs,
)
from job_assistant.services.parsing import (
    extract_job_from_text,
    extract_profile_from_resume,
    is_unsupported_listing_url,
    jobs_from_csv,
    read_uploaded_cv,
    unsupported_listing_message,
)
from job_assistant.services.public_discovery import discover_public_opportunities
from job_assistant.services.scoring import score_job

load_dotenv()
init_db()

PUBLIC_DISCOVERY_SOURCES = [
    "RemoteJobs.org",
    "Arbeitnow",
    "Remotive",
    "Jobicy",
    "Hacker News Who is hiring",
]


def _app_base_url() -> str:
    """Public URL used as the Google OAuth redirect URI."""
    try:
        configured_url = st.secrets.get("APP_BASE_URL")
    except st.errors.StreamlitSecretNotFoundError:
        configured_url = None
    return configured_url or settings.app_base_url


def _query_param_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""

st.set_page_config(page_title="Opportunity Assistant", page_icon="🚀", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; max-width: 1280px;}
    [data-testid="stSidebar"] {background: #0f172a;}
    [data-testid="stSidebar"] * {color: #e5e7eb;}
    .stButton > button, .stDownloadButton > button {border-radius: 10px; font-weight: 600;}
    div[data-testid="metric-container"] {background: #ffffff; border: 1px solid #e2e8f0; padding: 1rem; border-radius: 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);}
    .section-card {background:#fff; border:1px solid #e2e8f0; border-radius:18px; padding:1rem 1.2rem; margin:.75rem 0; box-shadow:0 1px 2px rgba(15,23,42,.05);}
    .muted-pill {display:inline-block; padding:.25rem .6rem; border-radius:999px; background:#eef2ff; color:#3730a3; font-size:.82rem; font-weight:600;}
    </style>
    """,
    unsafe_allow_html=True,
)


def get_cookie_manager():
    if "cookie_manager" in st.session_state:
        return st.session_state["cookie_manager"]
    try:
        import extra_streamlit_components as stx

        manager = stx.CookieManager(key="job_assistant_cookie_manager")
        st.session_state["cookie_manager"] = manager
        return manager
    except Exception:
        return None


cookie_manager = get_cookie_manager()


def _set_refresh_cookie(refresh_token: str) -> None:
    if not cookie_manager or not refresh_token:
        return
    cookie_manager.set(
        settings.session_cookie_name,
        refresh_token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
        same_site="lax",
        secure=settings.session_cookie_secure,
    )


def persist_login(user: dict) -> None:
    token = create_access_token(user)
    refresh_token = create_refresh_token(user, days=settings.refresh_token_expire_days)
    st.session_state["user"] = public_user(user)
    st.session_state["access_token"] = token
    _set_refresh_cookie(refresh_token)


def require_streamlit_user() -> dict:
    if st.session_state.get("user"):
        return st.session_state["user"]
    if cookie_manager:
        cookies = cookie_manager.get_all()
        refresh_token = cookies.get(settings.session_cookie_name) or cookie_manager.get(settings.session_cookie_name)
        if refresh_token:
            user = user_from_refresh_token(refresh_token)
            if user:
                st.session_state["user"] = public_user(user)
                st.session_state["access_token"] = create_access_token(user)
                _set_refresh_cookie(refresh_token)
                return st.session_state["user"]
        if not st.session_state.get("cookie_probe_done"):
            st.session_state["cookie_probe_done"] = True
            st.rerun()

    st.markdown(
        """
        <style>
        .auth-container {
            max-width: 980px;
            margin: 0 auto;
            padding-top: 1.5rem;
        }

        .auth-hero {
            background: linear-gradient(135deg, #eef4ff 0%, #f8fbff 100%);
            border: 1px solid #dbeafe;
            border-radius: 22px;
            padding: 2rem;
            margin-bottom: 1.5rem;
        }

        .auth-hero h1 {
            color: #000000;
            font-size: 2.1rem;
            margin-bottom: 0.4rem;
        }

        .auth-hero p {
            font-size: 1rem;
            color: #475569;
            margin-bottom: 0;
        }

        .security-card {
            background: #ecfdf5;
            border: 1px solid #bbf7d0;
            border-left: 6px solid #22c55e;
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 1rem 0;
            color: #14532d;
        }

        .demo-card {
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-left: 6px solid #f59e0b;
            border-radius: 16px;
            padding: 1rem 1.2rem;
            margin: 1rem 0;
            color: #78350f;
        }

        .auth-note {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 1rem;
            margin-top: 1rem;
            color: #334155;
        }

        .small-muted {
            color: #64748b;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="auth-container">', unsafe_allow_html=True)

    if not cookie_manager:
        st.warning(
            "Persistent login is not active because `extra-streamlit-components` is not installed "
            "in the environment running Streamlit. Run `pip install -r requirements.txt` and restart the app."
        )

    st.markdown(
        """
        <div class="auth-hero">
            <h1>Human-in-the-loop Opportunity Assistant</h1>
            <p>
                Sign in to manage your jobs, opportunities, reminders, profile, and generated materials safely.
                Your account keeps your data separated from other users.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    

    left_col, right_col = st.columns([1.1, 0.9], gap="large")

    with left_col:
        st.subheader("Welcome")
        st.write(
            """
            This assistant helps you track jobs, competitions, hackathons, webinars, and other opportunities.
            It is designed to keep you in control.
            """
        )

        st.markdown(
            """
            <div class="auth-note">
                <strong>Why registration is required</strong><br>
                Registration makes sure that saved data belongs to the correct user.
                This is especially important for the Privacy section, because deleting data should only delete
                the records connected to the currently signed-in account.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="security-card">
                <strong>Your data is secure and user-specific.</strong><br>
                Your profile, saved opportunities, evaluations, generated materials, statuses, notes, and reminders
                are linked to your registered account.
            </div>
            """,
            unsafe_allow_html=True,
        )


        st.markdown(
            """
            <div class="demo-card">
                <strong>This product is currently in demo phase.</strong><br>
                You can test the assistant safely. If you want to remove your data completely, go to the
                <strong>Privacy</strong> page after signing in and choose <strong>Delete my stored data</strong>.
                This removes data for the currently signed-in user only.
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <p class="small-muted">
                The app does not auto-apply to jobs, does not click submit buttons, and does not scrape private pages.
            </p>
            """,
            unsafe_allow_html=True,
        )

    with right_col:
        st.subheader("Access your workspace")

        login_tab, register_tab = st.tabs(["Sign in", "Create account"])

        with login_tab:
            with st.form("login_form"):
                email = st.text_input("Email", placeholder="you@example.com")
                password = st.text_input("Password", type="password", placeholder="Enter your password")

                submitted = st.form_submit_button("Sign in", use_container_width=True)

                if submitted:
                    user = authenticate_user(email, password)
                    if user:
                        persist_login(user)
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")

        with register_tab:
            with st.form("register_form"):
                full_name = st.text_input("Full name", placeholder="Your name")
                email = st.text_input("Email", key="register_email", placeholder="you@example.com")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="register_password",
                    placeholder="At least 8 characters",
                )

                accepted_demo_notice = st.checkbox(
                    "I understand this is a demo phase and I can delete my stored data from the Privacy page."
                )

                submitted = st.form_submit_button("Create account", use_container_width=True)

                if submitted:
                    if not full_name.strip():
                        st.error("Please enter your full name.")
                    elif not email.strip():
                        st.error("Please enter your email address.")
                    elif len(password) < 8:
                        st.error("Password must be at least 8 characters.")
                    elif not accepted_demo_notice:
                        st.error("Please confirm that you understand the demo and data deletion notice.")
                    else:
                        try:
                            user = register_user(email, password, full_name)
                            persist_login(user)
                            st.rerun()
                        except ValueError as exc:
                            st.error(str(exc))

    st.markdown("</div>", unsafe_allow_html=True)

    st.stop()

current_user = require_streamlit_user()
current_user_id = int(current_user["id"])

with st.sidebar:
    st.write(f"**Signed in:** {current_user['email']}")
    if st.button("Logout"):
        if cookie_manager:
            refresh_token = cookie_manager.get(settings.session_cookie_name)
            if refresh_token:
                revoke_refresh_token(refresh_token)
            cookie_manager.delete(settings.session_cookie_name)
        st.session_state.clear()
        st.rerun()
    st.divider()
    page = st.radio("Navigate", ["Profile", "Automation", "AI Orchestration", "Integrations", "Team", "Ingest Opportunities", "Review Queue", "Opportunity Detail", "Reminders", "Feedback", "Privacy"])
    st.divider()
    with st.expander("Quick feedback"):
        with st.form("quick_feedback_form"):
            q_category = st.selectbox("Category", FEEDBACK_CATEGORIES, index=FEEDBACK_CATEGORIES.index("General Suggestion"))
            q_title = st.text_input("Title", placeholder="Short summary")
            q_description = st.text_area("Details", height=90, placeholder="What happened or what should improve?")
            q_severity = st.selectbox("Severity", FEEDBACK_SEVERITIES, index=FEEDBACK_SEVERITIES.index("medium"))
            if st.form_submit_button("Submit feedback"):
                try:
                    create_feedback(current_user_id, {
                        "category": q_category,
                        "title": q_title,
                        "description": q_description,
                        "severity": q_severity,
                        "app_version": settings.app_version,
                        "metadata": {"source": "sidebar", "page": page},
                    })
                    st.success("Feedback submitted.")
                except Exception as exc:
                    st.error(f"Feedback failed: {exc}")
    st.divider()
    prefs_sidebar = get_automation_preferences(current_user_id)
    st.write("**Automation**")
    st.caption("Configured from the Automation page. Private sites are never scraped or auto-applied.")
    auto_col1, auto_col2 = st.columns(2)
    with auto_col1:
        if st.button("Start", key="start_scheduler"):
            try:
                from job_assistant.scheduler import start_scheduler

                start_scheduler(current_user_id)
                st.session_state["scheduler_started"] = True
                st.success("Scheduler started.")
            except Exception as exc:
                st.error(f"Scheduler failed: {exc}")
    with auto_col2:
        if st.button("Stop", key="stop_scheduler"):
            try:
                from job_assistant.scheduler import stop_scheduler

                stop_scheduler(current_user_id)
                st.session_state["scheduler_started"] = False
                st.success("Scheduler stopped.")
            except Exception as exc:
                st.error(f"Scheduler failed: {exc}")
    st.caption("Status: running" if st.session_state.get("scheduler_started") else ("Configured but stopped" if prefs_sidebar.get("enabled") else "Disabled"))
    st.divider()
    st.write("**Allowed workflow**")
    st.write("Process alerts, pasted descriptions, public/manual URLs, CSVs, and optional Gmail read-only messages.")
    st.write("For LinkedIn: open the URL yourself, review, and apply manually.")

reminders = due_reminders(current_user_id)
if reminders:
    st.warning(f"You have {len(reminders)} due reminder(s). Open Reminders to review them.")

if page == "Automation":
    st.header("Automation control center")
    prefs = get_automation_preferences(current_user_id)
    c1, c2, c3, c4 = st.columns(4)
    jobs_count = len(list_jobs(current_user_id))
    unread_events = len(list_activity_events(current_user_id, unread_only=True))
    c1.metric("Automation", "Enabled" if prefs.get("enabled") else "Disabled")
    c2.metric("Saved opportunities", jobs_count)
    c3.metric("Unread updates", unread_events)
    c4.metric("Min score", prefs.get("min_score_for_materials", 70))

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("Workflow preferences")
    with st.form("automation_preferences"):
        enabled = st.toggle("Enable scheduled automation", value=bool(prefs.get("enabled")))
        gmail_enabled = st.toggle("Import Gmail alerts automatically", value=bool(prefs.get("gmail_enabled")))
        public_sources_enabled = st.toggle("Discover public opportunities automatically", value=bool(prefs.get("public_sources_enabled")))
        linkedin_api_enabled = st.toggle("Search LinkedIn jobs API automatically", value=bool(prefs.get("linkedin_api_enabled")))
        score_new = st.toggle("Score every new opportunity", value=bool(prefs.get("score_new")))
        generate_materials_pref = st.toggle("Generate application materials for high-match jobs", value=bool(prefs.get("generate_materials")))
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            gmail_interval_minutes = st.number_input("Gmail interval minutes", min_value=5, max_value=1440, value=int(prefs.get("gmail_interval_minutes", 30)), step=5)
        with col_b:
            public_interval_hours = st.number_input("Public discovery interval hours", min_value=1, max_value=168, value=int(prefs.get("public_interval_hours", 6)), step=1)
        with col_c:
            linkedin_interval_hours = st.number_input("LinkedIn API interval hours", min_value=1, max_value=168, value=int(prefs.get("linkedin_interval_hours", 6)), step=1)
        with col_d:
            daily_summary_hour = st.number_input("Daily summary hour", min_value=0, max_value=23, value=int(prefs.get("daily_summary_hour", 8)), step=1)
        min_score_for_materials = st.slider("Generate materials only when score is at least", 0, 100, int(prefs.get("min_score_for_materials", 70)))
        notify_in_app = st.toggle("Show in-app progress notifications", value=bool(prefs.get("notify_in_app")))
        if st.form_submit_button("Save automation preferences", use_container_width=True):
            save_automation_preferences(current_user_id, {
                "enabled": enabled,
                "gmail_enabled": gmail_enabled,
                "public_sources_enabled": public_sources_enabled,
                "linkedin_api_enabled": linkedin_api_enabled,
                "score_new": score_new,
                "generate_materials": generate_materials_pref,
                "gmail_interval_minutes": gmail_interval_minutes,
                "public_interval_hours": public_interval_hours,
                "linkedin_interval_hours": linkedin_interval_hours,
                "daily_summary_hour": daily_summary_hour,
                "min_score_for_materials": min_score_for_materials,
                "notify_in_app": notify_in_app,
            })
            st.success("Automation preferences saved. Restart the scheduler for interval changes to take effect.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("Recent progress updates")
    events = list_activity_events(current_user_id, limit=20)
    if events:
        st.dataframe(pd.DataFrame(events)[["created_at", "level", "title", "message"]], use_container_width=True, hide_index=True)
    else:
        st.info("No automation updates yet. Start the scheduler after enabling automation.")

elif page == "Profile":
    st.header("1. User profile setup")
    profile = get_profile(current_user_id)
    uploaded_cv = st.file_uploader("Upload CV/resume (.pdf, .docx, .txt)", type=["pdf", "docx", "txt"])
    if uploaded_cv:
        cv_text = read_uploaded_cv(uploaded_cv)
        st.session_state["profile_draft"] = {**profile, **extract_profile_from_resume(cv_text, user_id=current_user_id)}
        st.success("Resume parsed. Review/edit the auto-filled fields below before saving.")
    profile_values = {**profile, **st.session_state.get("profile_draft", {})}
    with st.form("profile_form"):
        cv_text = st.text_area("CV / resume text", value=profile_values.get("cv_text", ""), height=220)
        target_roles = st.text_input("Target roles", value=profile_values.get("target_roles", ""))
        industries = st.text_input("Target industries", value=profile_values.get("industries", ""))
        locations = st.text_input("Locations", value=profile_values.get("locations", ""))
        remote_preference = st.text_input("Remote preference", value=profile_values.get("remote_preference", ""))
        salary_expectations = st.text_input("Salary expectations", value=profile_values.get("salary_expectations", ""))
        work_authorization = st.text_input("Visa/work authorization", value=profile_values.get("work_authorization", ""))
        years_experience = st.text_input("Years of experience", value=profile_values.get("years_experience", ""))
        skills = st.text_area("Skills", value=profile_values.get("skills", ""), height=90)
        deal_breakers = st.text_area("Deal-breakers", value=profile_values.get("deal_breakers", ""), height=90)
        if st.form_submit_button("Save profile"):
            upsert_profile(locals(), current_user_id)
            st.session_state.pop("profile_draft", None)
            st.success("Profile saved locally.")

elif page == "AI Orchestration":
    st.header("AI Orchestration & Workflow Automation")
    st.write("Phase 4 and 5 controls for AI generation logging, prompt versions, and safe automation rules.")
    ai_log_tab, prompt_tab, rules_tab, runs_tab = st.tabs(["AI usage", "Prompt versions", "Automation rules", "Automation runs"])

    with ai_log_tab:
        generations = list_ai_generations(current_user_id, limit=100)
        if generations:
            st.dataframe(pd.DataFrame(generations), use_container_width=True, hide_index=True)
        else:
            st.info("No AI generations logged yet. AI calls will appear here with provider, model, task type, latency, and status.")

    with prompt_tab:
        with st.form("prompt_version_form"):
            name = st.text_input("Prompt name", value="opportunity_summary")
            version = st.text_input("Version", value="v1")
            description = st.text_input("Description", value="Reusable prompt template")
            template = st.text_area("Template", value="Summarize this opportunity as JSON.", height=180)
            is_active = st.checkbox("Active", value=True)
            if st.form_submit_button("Save prompt version"):
                upsert_prompt_version(name, version, template, description, is_active)
                st.success("Prompt version saved.")
                st.rerun()
        prompts = list_prompt_versions()
        if prompts:
            st.dataframe(pd.DataFrame(prompts), use_container_width=True, hide_index=True)

    with rules_tab:
        existing_rules = list_automation_rules(current_user_id, include_inactive=True)
        if existing_rules:
            st.dataframe(pd.DataFrame(existing_rules), use_container_width=True, hide_index=True)
        else:
            st.info("No automation rules yet. Create one below. Human approval is enabled by default.")
        with st.form("automation_rule_form"):
            rule_name = st.text_input("Rule name", value="Notify on high score opportunity")
            trigger_event = st.selectbox("Trigger event", ["manual", "feedback.created", "opportunity.created", "high_score_opportunity", "provider.failed", "ai.generated"], index=0)
            action_type = st.selectbox("Action type", ["notify", "draft", "webhook"], index=0)
            message = st.text_input("Notification message", value="Automation matched. Review before taking action.")
            human_approval_required = st.checkbox("Require human approval", value=True)
            is_active = st.checkbox("Rule active", value=True)
            if st.form_submit_button("Create automation rule"):
                create_automation_rule(current_user_id, {"name": rule_name, "trigger_event": trigger_event, "action_type": action_type, "action_config": {"message": message}, "is_active": is_active, "human_approval_required": human_approval_required})
                st.success("Automation rule created.")
                st.rerun()
        if existing_rules:
            labels = {f"#{r['id']} {r['name']}": r for r in existing_rules}
            selected = st.selectbox("Delete automation rule", ["Select..."] + list(labels.keys()))
            if selected != "Select..." and st.button("Delete selected automation rule"):
                delete_automation_rule(int(labels[selected]["id"]), current_user_id)
                st.success("Automation rule deleted.")
                st.rerun()
        with st.form("manual_trigger_form"):
            manual_event = st.text_input("Trigger event to test", value="manual")
            payload_json = st.text_area("Payload JSON", value='{"source":"manual_test"}', height=120)
            if st.form_submit_button("Run trigger"):
                try:
                    results = automation_engine.trigger(current_user_id, manual_event, json.loads(payload_json or "{}"))
                    st.success("Automation trigger executed.")
                    st.json(results)
                except Exception as exc:
                    st.error(f"Automation trigger failed: {exc}")

    with runs_tab:
        runs = list_automation_runs(current_user_id, limit=100)
        errors = list_automation_errors(current_user_id, limit=100)
        if runs:
            st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
        else:
            st.info("No automation runs yet.")
        if errors:
            st.subheader("Automation errors")
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

elif page == "Integrations":
    st.header("Integrations")
    st.success("API keys and sensitive integration settings are encrypted before they are stored. Use least-privilege keys and rotate them regularly.")
    ai_tab, providers_tab, linkedin_tab, rapidapi_tab, apify_tab = st.tabs(["AI provider", "Provider registry", "LinkedIn posting", "RapidAPI LinkedIn jobs", "Apify scraping"])

    with ai_tab:
        st.subheader("Multi-provider AI")
        ai = get_integration_settings(current_user_id, "ai_provider")
        ai_config = ai.get("config", {})
        provider_keys = list(SUPPORTED_PROVIDERS.keys())
        current_provider = ai_config.get("provider", settings.default_ai_provider)
        with st.form("ai_provider_settings"):
            provider = st.selectbox("Provider", provider_keys, index=provider_keys.index(current_provider) if current_provider in provider_keys else 0, format_func=lambda k: SUPPORTED_PROVIDERS[k])
            model = st.text_input("Model / deployment", value=ai_config.get("model", settings.openai_model))
            api_key = st.text_input("Provider API key", value="", type="password", placeholder="Leave blank to keep the saved key")
            base_url = st.text_input("Base URL (OpenAI-compatible/Grok optional)", value=ai_config.get("base_url", ""))
            azure_endpoint = st.text_input("Azure endpoint", value=ai_config.get("endpoint", ""), placeholder="https://your-resource.openai.azure.com")
            azure_api_version = st.text_input("Azure API version", value=ai_config.get("api_version", "2024-10-21"))
            deployment = st.text_input("Azure deployment name", value=ai_config.get("deployment", ""))
            hf_endpoint = st.text_input("Hugging Face endpoint override", value=ai_config.get("endpoint", "") if provider == "huggingface" else "")
            if st.form_submit_button("Save AI provider", use_container_width=True):
                config = {
                    "provider": provider,
                    "model": model,
                    "base_url": base_url,
                    "endpoint": hf_endpoint if provider == "huggingface" else azure_endpoint,
                    "api_version": azure_api_version,
                    "deployment": deployment,
                }
                save_integration_settings(current_user_id, "ai_provider", api_key, config, keep_existing_api_key_if_blank=True)
                st.success("AI provider settings saved securely.")
                st.rerun()
        st.caption(f"Stored key status: {mask_secret(ai.get('api_key', ''))}")

        if st.button("Remove AI provider settings"):
            delete_integration_settings(current_user_id, "ai_provider")
            st.success("AI provider settings removed.")
            st.rerun()

    with providers_tab:
        st.subheader("Provider abstraction registry")
        st.write("Register user-owned providers by platform, priority, and auth type. Credentials are encrypted per user and can be used for fallback routing as integrations are migrated to provider adapters.")
        current_providers = list_provider_configs(current_user_id)
        if current_providers:
            display_rows = []
            for item in current_providers:
                display_rows.append({
                    "platform": item.get("platform"),
                    "provider_name": item.get("provider_name"),
                    "auth_type": item.get("auth_type"),
                    "priority": item.get("priority"),
                    "active": item.get("is_active"),
                    "health": item.get("health_status"),
                    "has_credentials": item.get("has_credentials"),
                    "success_count": item.get("success_count"),
                    "failure_count": item.get("failure_count"),
                    "updated_at": item.get("updated_at"),
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No provider-registry records yet. Add one below. Existing legacy integrations continue to work while provider adapters are introduced.")

        with st.form("provider_registry_form"):
            st.markdown("**Add or update provider**")
            col_a, col_b, col_c = st.columns([1, 1, 1])
            with col_a:
                platform = st.text_input("Platform", value="ai", placeholder="ai, linkedin, reddit, custom_cms")
            with col_b:
                provider_name = st.text_input("Provider name", value="openai", placeholder="openai, rapidapi, apify, custom_proxy")
            with col_c:
                auth_type = st.selectbox("Auth type", ["api_key", "bearer_token", "oauth2", "custom_headers", "webhook_secret", "basic_auth"], index=0)
            credential_value = st.text_input("Secret / token / API key", value="", type="password", placeholder="Leave blank to keep saved credentials")
            priority = st.number_input("Priority", min_value=1, max_value=1000, value=100, step=1, help="Lower number is tried first during fallback.")
            is_active = st.checkbox("Active", value=True)
            config_json = st.text_area("Provider config JSON", value='{\n  "supported_actions": ["health_check"]\n}', height=130)
            if st.form_submit_button("Save provider registry record", use_container_width=True):
                try:
                    parsed_config = json.loads(config_json or "{}")
                    credential_key = "access_token" if auth_type in {"bearer_token", "oauth2"} else "api_key"
                    credentials = {credential_key: credential_value} if credential_value.strip() else {}
                    save_provider_config(
                        current_user_id,
                        platform,
                        provider_name,
                        auth_type=auth_type,
                        credentials=credentials,
                        config=parsed_config,
                        priority=int(priority),
                        is_active=is_active,
                        keep_existing_credentials_if_blank=True,
                    )
                    st.success("Provider registry record saved securely.")
                    st.rerun()
                except json.JSONDecodeError as exc:
                    st.error(f"Provider config JSON is invalid: {exc}")
                except Exception as exc:
                    st.error(f"Could not save provider: {exc}")

        if current_providers:
            labels = {f"{p['platform']} / {p['provider_name']}": p for p in current_providers}
            selected_label = st.selectbox("Remove provider", ["Select..."] + list(labels.keys()))
            if selected_label != "Select..." and st.button("Delete selected provider registry record"):
                item = labels[selected_label]
                delete_provider_config(current_user_id, item["platform"], item["provider_name"])
                st.success("Provider registry record deleted.")
                st.rerun()

    with linkedin_tab:
        st.subheader("LinkedIn official API posting")
        st.write("This uses LinkedIn's official post API. Your LinkedIn app/token must have the required posting scope, such as `w_member_social` for member posts.")
        linkedin = get_integration_settings(current_user_id, "linkedin")
        linkedin_config = linkedin.get("config", {})
        with st.form("linkedin_settings"):
            linkedin_token = st.text_input("LinkedIn OAuth access token", value="", type="password", placeholder="Leave blank to keep the saved token")
            author_urn = st.text_input("Author URN", value=linkedin_config.get("author_urn", ""), placeholder="urn:li:person:... or urn:li:organization:...")
            linkedin_version = st.text_input("LinkedIn API version", value=linkedin_config.get("linkedin_version", "202604"))
            if st.form_submit_button("Save LinkedIn settings"):
                save_integration_settings(
                    current_user_id,
                    "linkedin",
                    linkedin_token,
                    {"author_urn": author_urn, "linkedin_version": linkedin_version},
                    keep_existing_api_key_if_blank=True,
                )
                st.success("LinkedIn settings saved.")

        post_text = st.text_area("Post text", height=180, placeholder="Write a LinkedIn post to publish through the official API.")
        if st.button("Publish LinkedIn post", disabled=not post_text.strip()):
            linkedin = get_integration_settings(current_user_id, "linkedin")
            try:
                result = publish_text_post(
                    linkedin.get("api_key", ""),
                    linkedin.get("config", {}).get("author_urn", ""),
                    post_text,
                    linkedin.get("config", {}).get("linkedin_version", "202604"),
                )
                st.success(f"Published. Post id: {result.get('post_id') or 'returned by LinkedIn headers'}")
            except Exception as exc:
                st.error(f"LinkedIn publish failed: {exc}")

        if st.button("Remove LinkedIn settings"):
            delete_integration_settings(current_user_id, "linkedin")
            st.success("LinkedIn settings removed.")
            st.rerun()

    with rapidapi_tab:
        st.subheader("RapidAPI LinkedIn jobs")
        st.write("Use a third-party RapidAPI key to import LinkedIn job search results. Rotate any key that has been shared publicly.")
        rapidapi = get_integration_settings(current_user_id, "rapidapi_linkedin")
        rapidapi_config = rapidapi.get("config", {})
        with st.form("rapidapi_linkedin_settings"):
            rapidapi_key = st.text_input("RapidAPI key", value="", type="password", placeholder="Leave blank to keep the saved key")
            rapidapi_host = st.text_input("RapidAPI host", value=rapidapi_config.get("host", RAPIDAPI_LINKEDIN_HOST))
            rapidapi_endpoint = st.text_input("Endpoint URL", value=rapidapi_config.get("endpoint", RAPIDAPI_LINKEDIN_ENDPOINT))
            title_filter_default = rapidapi_config.get("title_filter", "")
            location_filter_default = rapidapi_config.get("location_filter", "Remote")
            title_filter_saved = st.text_input("Default automated title/search filter", value=title_filter_default, placeholder="Software Engineer OR Data Analyst")
            location_filter_saved = st.text_input("Default automated location filter", value=location_filter_default, placeholder="Remote OR United States")
            max_offsets_saved = st.number_input("Automated API offsets per run", min_value=1, max_value=20, value=int(rapidapi_config.get("max_offsets", 1)), step=1)
            if st.form_submit_button("Save RapidAPI settings"):
                save_integration_settings(
                    current_user_id,
                    "rapidapi_linkedin",
                    rapidapi_key,
                    {
                        "host": rapidapi_host,
                        "endpoint": rapidapi_endpoint,
                        "title_filter": title_filter_saved,
                        "location_filter": location_filter_saved,
                        "max_offsets": int(max_offsets_saved),
                    },
                    keep_existing_api_key_if_blank=True,
                )
                st.success("RapidAPI settings saved.")

        if st.button("Remove RapidAPI settings"):
            delete_integration_settings(current_user_id, "rapidapi_linkedin")
            st.success("RapidAPI settings removed.")
            st.rerun()

    with apify_tab:
        st.subheader("Apify actor settings")
        st.write("Use your own Apify token and actor. Different actors expect different input JSON, so this app lets you configure the actor id and input template.")
        apify = get_integration_settings(current_user_id, "apify")
        apify_config = apify.get("config", {})
        default_template = apify_config.get("input_template") or '{\n  "startUrls": [{"url": "{{url}}"]}\n}'
        with st.form("apify_settings"):
            apify_token = st.text_input("Apify API token", value="", type="password", placeholder="Leave blank to keep the saved token")
            actor_id = st.text_input("Actor id", value=apify_config.get("actor_id", ""), placeholder="username/actor-name or actor id")
            input_template = st.text_area("Input JSON template", value=default_template, height=180)
            st.caption("Use `{{url}}` where the pasted job/listing URL should be inserted.")
            if st.form_submit_button("Save Apify settings"):
                try:
                    json.loads(input_template)
                    save_integration_settings(
                        current_user_id,
                        "apify",
                        apify_token,
                        {"actor_id": actor_id, "input_template": input_template},
                        keep_existing_api_key_if_blank=True,
                    )
                    st.success("Apify settings saved.")
                except json.JSONDecodeError as exc:
                    st.error(f"Input template is not valid JSON: {exc}")

        if st.button("Remove Apify settings"):
            delete_integration_settings(current_user_id, "apify")
            st.success("Apify settings removed.")
            st.rerun()


elif page == "Team":
    st.header("Team, Workspaces & RBAC")
    try:
        ensure_user_workspace(current_user_id)
        summary = enterprise_summary(current_user_id)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Workspaces", summary.get("workspaces", 0))
        c2.metric("Members", summary.get("members", 0))
        c3.metric("Shared resources", summary.get("shared_resources", 0))
        c4.metric("Permissions", summary.get("permissions", 0))

        tab_ws, tab_members, tab_share, tab_rbac, tab_admin = st.tabs(["Workspaces", "Members", "Shared resources", "RBAC", "Admin summary"])

        with tab_ws:
            st.subheader("Your workspaces")
            workspaces = list_user_workspaces(current_user_id)
            if workspaces:
                st.dataframe(pd.DataFrame(workspaces), use_container_width=True, hide_index=True)
            else:
                st.info("No workspaces yet.")
            st.divider()
            st.subheader("Create organization")
            with st.form("create_org_form"):
                org_name = st.text_input("Organization name")
                if st.form_submit_button("Create organization"):
                    try:
                        org = create_organization(current_user_id, org_name)
                        st.success(f"Created organization: {org['name']}")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            st.subheader("Create workspace")
            org_options = {f"{w['organization_name']} #{w['organization_id']}": int(w['organization_id']) for w in workspaces}
            with st.form("create_workspace_form"):
                if org_options:
                    selected_org = st.selectbox("Organization", list(org_options.keys()))
                    ws_name = st.text_input("Workspace name")
                    ws_desc = st.text_area("Description", height=80)
                    if st.form_submit_button("Create workspace"):
                        try:
                            ws = create_workspace(current_user_id, org_options[selected_org], ws_name, ws_desc)
                            st.success(f"Created workspace: {ws['name']}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    st.info("Create an organization first.")

        with tab_members:
            st.subheader("Workspace members")
            workspaces = list_user_workspaces(current_user_id)
            ws_options = {f"{w['name']} / {w['organization_name']} #{w['id']}": int(w['id']) for w in workspaces}
            if ws_options:
                selected_ws = st.selectbox("Workspace", list(ws_options.keys()), key="members_workspace")
                workspace_id = ws_options[selected_ws]
                try:
                    members = list_workspace_members(current_user_id, workspace_id)
                    st.dataframe(pd.DataFrame(members), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.warning(str(exc))
                st.divider()
                st.subheader("Add existing user")
                with st.form("add_member_form"):
                    member_email = st.text_input("User email")
                    role_names = [r["name"] for r in list_roles()]
                    member_role = st.selectbox("Role", role_names, index=role_names.index("viewer") if "viewer" in role_names else 0)
                    if st.form_submit_button("Add/update member"):
                        try:
                            added = add_workspace_member(current_user_id, workspace_id, member_email, member_role)
                            st.success(f"Member saved as {added['role']}")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
            else:
                st.info("No workspace available.")

        with tab_share:
            st.subheader("Share resources into a workspace")
            workspaces = list_user_workspaces(current_user_id)
            ws_options = {f"{w['name']} / {w['organization_name']} #{w['id']}": int(w['id']) for w in workspaces}
            if ws_options:
                with st.form("share_resource_form"):
                    selected_ws = st.selectbox("Workspace", list(ws_options.keys()), key="share_workspace")
                    resource_type = st.selectbox("Resource type", ["job", "feedback", "post", "workflow", "report", "dashboard", "document", "other"])
                    resource_id = st.text_input("Resource ID")
                    access_level = st.selectbox("Access level", ["read", "comment", "edit", "admin"])
                    expires_at = st.text_input("Expires at ISO timestamp", placeholder="optional")
                    if st.form_submit_button("Share resource"):
                        try:
                            share_resource(current_user_id, ws_options[selected_ws], resource_type, resource_id, access_level, expires_at)
                            st.success("Resource shared.")
                            st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                st.subheader("Shared resources")
                try:
                    resources = list_shared_resources(current_user_id)
                    if resources:
                        st.dataframe(pd.DataFrame(resources), use_container_width=True, hide_index=True)
                    else:
                        st.info("No shared resources yet.")
                except Exception as exc:
                    st.warning(str(exc))

        with tab_rbac:
            st.subheader("Roles")
            st.dataframe(pd.DataFrame(list_roles()), use_container_width=True, hide_index=True)
            st.subheader("Role permissions")
            st.dataframe(pd.DataFrame(list_role_permissions()), use_container_width=True, hide_index=True)
            st.subheader("Permission catalog")
            st.dataframe(pd.DataFrame(list_permissions()), use_container_width=True, hide_index=True)

        with tab_admin:
            st.subheader("Enterprise readiness snapshot")
            st.json(summary)
            st.caption("This is a foundation for team/enterprise administration. Full billing, SSO, and organization-wide policy enforcement remain future work.")
    except Exception as exc:
        st.error(f"Team workspace setup failed: {exc}")

elif page == "Ingest Opportunities":
    st.header("2. Opportunity source ingestion")
    source_tab, public_tab, rapidapi_tab, apify_tab, csv_tab, gmail_tab = st.tabs(["Manual / pasted", "Public discovery", "LinkedIn API", "Apify scraper", "CSV upload", "Gmail read-only"])

    with source_tab:
        st.subheader("Manual URL or pasted opportunity text")
        opportunity_type = st.selectbox("Opportunity type", OPPORTUNITY_TYPES, index=0)
        source = st.selectbox("Source", ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Devpost", "Eventbrite", "Meetup", "Other"])
        raw = st.text_area("Paste opportunity URL, email, or description", height=260)
        if st.button("Extract and save opportunity", disabled=not raw.strip()):
            if is_unsupported_listing_url(raw):
                st.error(unsupported_listing_message(raw))
                st.stop()
            job = extract_job_from_text(raw, source=source, opportunity_type=opportunity_type, user_id=current_user_id)
            job_id = insert_job(job, current_user_id)
            st.success(f"Saved {opportunity_type} #{job_id}: {job.get('title')} at {job.get('company')}")
            st.json(job)

    with public_tab:
        st.subheader("Public job discovery")
        st.write("Uses public no-auth job APIs. It avoids direct Indeed scraping and direct Devpost crawling.")
        public_query = st.text_input("Search keywords", value=profile.get("target_roles", "") if (profile := get_profile(current_user_id)) else "")
        public_sources = st.multiselect("Sources", PUBLIC_DISCOVERY_SOURCES, default=PUBLIC_DISCOVERY_SOURCES)
        public_limit = st.slider("Max per source", 1, 50, 20)
        if st.button("Find public jobs", disabled=not public_sources):
            try:
                found = discover_public_opportunities(public_query, public_sources, public_limit)
                st.session_state["public_discovery_results"] = found
                st.success(f"Found {len(found)} public job(s). Review before importing.")
            except Exception as exc:
                st.error(f"Public discovery failed: {exc}")

        found = st.session_state.get("public_discovery_results", [])
        if found:
            found_df = pd.DataFrame(found)
            st.dataframe(
                found_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in found_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import discovered jobs"):
                ids = [insert_job(item, current_user_id) for item in found]
                st.success(f"Imported {len(ids)} discovered job(s).")
                st.session_state["public_discovery_results"] = []

    with apify_tab:
        st.subheader("Apify scraper import")
        st.write("Runs your configured Apify actor against a URL, previews returned items, then imports them as jobs after review.")
        apify = get_integration_settings(current_user_id, "apify")
        apify_config = apify.get("config", {})
        if not apify.get("api_key") or not apify_config.get("actor_id"):
            st.info("Add your Apify API token and actor id in Integrations first.")
        scrape_url = st.text_input("Job/listing URL to send to Apify", placeholder="https://...")
        if st.button("Run Apify scraper", disabled=not scrape_url.strip() or not apify.get("api_key") or not apify_config.get("actor_id")):
            try:
                run_input = build_run_input(scrape_url, apify_config.get("input_template", ""))
                items = run_actor_for_items(apify["api_key"], apify_config["actor_id"], run_input)
                opportunities = apify_items_to_opportunities(items, source=f"Apify:{apify_config['actor_id']}")
                st.session_state["apify_results"] = opportunities
                st.success(f"Apify returned {len(items)} item(s); mapped {len(opportunities)} job(s). Review before importing.")
            except Exception as exc:
                st.error(f"Apify scraper failed: {exc}")

        apify_results = st.session_state.get("apify_results", [])
        if apify_results:
            apify_df = pd.DataFrame(apify_results)
            st.dataframe(
                apify_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in apify_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import Apify jobs"):
                ids = [insert_job(item, current_user_id) for item in apify_results]
                st.success(f"Imported {len(ids)} Apify job(s).")
                st.session_state["apify_results"] = []

    with rapidapi_tab:
        st.subheader("LinkedIn job API import")
        st.write("Uses your configured RapidAPI LinkedIn job search API. It imports API results, not direct LinkedIn page scraping.")
        rapidapi = get_integration_settings(current_user_id, "rapidapi_linkedin")
        rapidapi_config = rapidapi.get("config", {})
        if not rapidapi.get("api_key"):
            st.info("Add your RapidAPI key in Integrations first.")
        col_a, col_b, col_c = st.columns([2, 2, 1])
        with col_a:
            title_filter = st.text_input("Title filter", value=get_profile(current_user_id).get("target_roles", ""))
        with col_b:
            location_filter = st.text_input("Location filter", value="United States OR United Kingdom")
        with col_c:
            offset = st.number_input("Offset", min_value=0, value=0, step=1)
        if st.button("Search LinkedIn jobs API", disabled=not rapidapi.get("api_key") or not title_filter.strip()):
            try:
                items = search_linkedin_jobs(
                    rapidapi["api_key"],
                    title_filter,
                    location_filter,
                    int(offset),
                    rapidapi_config.get("host", RAPIDAPI_LINKEDIN_HOST),
                    rapidapi_config.get("endpoint", RAPIDAPI_LINKEDIN_ENDPOINT),
                )
                jobs = rapidapi_items_to_opportunities(items)
                st.session_state["rapidapi_linkedin_results"] = jobs
                st.success(f"API returned {len(items)} item(s); mapped {len(jobs)} job(s). Review before importing.")
            except Exception as exc:
                st.error(f"LinkedIn API search failed: {exc}")

        rapidapi_results = st.session_state.get("rapidapi_linkedin_results", [])
        if rapidapi_results:
            rapidapi_df = pd.DataFrame(rapidapi_results)
            st.dataframe(
                rapidapi_df[[c for c in ["title", "company", "location", "source", "url", "description"] if c in rapidapi_df.columns]],
                use_container_width=True,
                hide_index=True,
            )
            if st.button("Import LinkedIn API jobs"):
                ids = [insert_job(item, current_user_id) for item in rapidapi_results]
                st.success(f"Imported {len(ids)} LinkedIn API job(s).")
                st.session_state["rapidapi_linkedin_results"] = []

    with csv_tab:
        st.subheader("CSV upload")
        st.write("Expected columns include title, company, location, remote_type, url, source, description, salary_min, salary_max, deadline, opportunity_type. Extra columns are ignored.")
        csv_opportunity_type = st.selectbox("Default CSV opportunity type", OPPORTUNITY_TYPES, index=0)
        uploaded = st.file_uploader("Upload opportunities CSV", type=["csv"])
        if uploaded and st.button("Import CSV opportunities"):
            jobs = jobs_from_csv(uploaded, default_opportunity_type=csv_opportunity_type)
            ids = [insert_job(j, current_user_id) for j in jobs]
            st.success(f"Imported {len(ids)} opportunity/opportunities.")

    with gmail_tab:
        st.subheader("Gmail alerts")
        st.write("Each user connects their own Gmail account. OAuth tokens are encrypted per user and the scheduler only reads the Gmail mailbox connected by the currently logged-in user.")

        redirect_uri = _app_base_url().rstrip("/")
        oauth_code = _query_param_value("code")
        oauth_state = _query_param_value("state")
        if oauth_code and oauth_state and not st.session_state.get("gmail_oauth_done"):
            try:
                exchange_gmail_code(current_user_id, oauth_code, redirect_uri, oauth_state)
                st.session_state["gmail_oauth_done"] = True
                st.query_params.clear()
                st.success("Gmail connected for your account.")
            except Exception as exc:
                st.error(f"Gmail connection failed: {exc}")

        gmail_connection = get_gmail_connection(current_user_id)
        if gmail_connection.get("connected"):
            connected_as = gmail_connection.get("connected_email") or "connected Gmail account"
            st.success(f"Gmail connected: {connected_as}")
            if st.button("Disconnect Gmail"):
                disconnect_gmail(current_user_id)
                st.success("Gmail disconnected for your account.")
                st.rerun()
        else:
            st.info("Gmail is not connected for this user yet.")
            try:
                auth_url = build_gmail_authorization_url(current_user_id, redirect_uri)
                st.link_button("Connect Gmail", auth_url)
                st.caption(f"Google OAuth redirect URI: `{redirect_uri}`. Add this exact URL to the Google Cloud OAuth client.")
            except Exception as exc:
                st.warning(f"Gmail OAuth is not configured yet: {exc}")

        gmail_opportunity_type = st.selectbox("Classify Gmail results as", ["auto", *OPPORTUNITY_TYPES], index=0)
        query = st.text_input("Gmail search query", value='("job alert" OR "new jobs" OR recruiter OR "is hiring" OR hackathon OR webinar OR competition OR contest OR challenge) newer_than:30d')
        max_results = st.slider("Max emails", 1, 50, 10)
        if st.button("Fetch Gmail alerts"):
            try:
                messages = fetch_job_alert_messages(user_id=current_user_id, query=query, max_results=max_results)
                count = 0
                for m in messages:
                    job = extract_job_from_text(
                        f"Subject: {m['subject']}\nFrom: {m['from']}\n\n{m['body']}",
                        source="Gmail",
                        opportunity_type=gmail_opportunity_type,
                        user_id=current_user_id,
                    )
                    job["date_received"] = m.get("date_received", "")
                    insert_job(job, current_user_id)
                    count += 1
                st.success(f"Imported {count} Gmail-derived opportunity/opportunities.")
            except Exception as exc:
                st.error(f"Gmail ingestion failed: {exc}")

elif page == "Review Queue":
    st.header("5. Review queue")
    jobs = list_jobs(current_user_id)
    if not jobs:
        st.info("No opportunities yet. Add them from Ingest Opportunities.")
    else:
        df = pd.DataFrame(jobs)
        visible_cols = ["id", "opportunity_type", "title", "company", "location", "source", "url", "match_score", "priority", "status", "deadline", "notes", "cover_letter", "screening_answers", "updated_at"]
        table_df = df[[c for c in visible_cols if c in df.columns]].copy()
        table_df.insert(0, "delete", False)
        edited_df = st.data_editor(
            table_df,
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in table_df.columns if c != "delete"],
            column_config={"delete": st.column_config.CheckboxColumn("Select", help="Select rows to delete")},
            key="review_queue_editor",
        )
        selected_delete_ids = edited_df.loc[edited_df["delete"], "id"].astype(int).tolist()
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Score all unscored opportunities"):
                profile = get_profile(current_user_id)
                if not profile:
                    st.error("Create your profile first.")
                else:
                    n = 0
                    for row in jobs:
                        if row.get("match_score") is None:
                            evaluation = score_job(profile, row, user_id=current_user_id)
                            save_evaluation(row["id"], evaluation, current_user_id)
                            n += 1
                    st.success(f"Scored {n} opportunity/opportunities.")
                    st.rerun()
        with col2:
            if selected_delete_ids:
                st.warning(f"{len(selected_delete_ids)} selected for deletion.")
                if st.button("Delete selected opportunities"):
                    for selected_id in selected_delete_ids:
                        delete_job(selected_id, current_user_id)
                    st.success(f"Deleted {len(selected_delete_ids)} opportunity/opportunities.")
                    st.rerun()
            else:
                st.write("Select rows in the table to delete, or open Opportunity Detail to edit one item.")

elif page == "Opportunity Detail":
    st.header("4. Opportunity detail")
    jobs = list_jobs(current_user_id)
    if not jobs:
        st.info("No opportunities available.")
    else:
        labels = {f"#{j['id']} [{j.get('opportunity_type', 'job')}] - {j['title']} @ {j.get('company','')}": j["id"] for j in jobs}
        selected = st.selectbox("Select opportunity", list(labels.keys()))
        job_id = labels[selected]
        job = get_job(job_id, current_user_id)
        profile = get_profile(current_user_id)
        evaluation = get_evaluation(job_id, current_user_id)
        materials = get_materials(job_id, current_user_id)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("Opportunity")
            st.write(f"**Type:** {job.get('opportunity_type', 'job')}")
            st.write(f"**{job.get('title')}**")
            st.write(job.get("company", ""))
            st.write(job.get("location", ""))
            if job.get("url"):
                st.link_button("Open URL for manual review", job["url"])
            st.text_area("Description", value=job.get("description", ""), height=220)
            if st.button("Delete this opportunity"):
                delete_job(job_id, current_user_id)
                st.success("Opportunity deleted.")
                st.rerun()

        with col2:
            st.subheader("Evaluation")
            if st.button("Score / rescore opportunity"):
                if not profile:
                    st.error("Create your profile first.")
                else:
                    evaluation = score_job(profile, job, user_id=current_user_id)
                    save_evaluation(job_id, evaluation, current_user_id)
                    st.success("Score saved.")
                    st.rerun()
            if evaluation:
                st.metric("Match score", evaluation.get("match_score", 0))
                st.write(f"**Priority:** {evaluation.get('priority', '')}")
                st.write("**Good fit:**", evaluation.get("good_fit", ""))
                st.write("**Weak areas:**", evaluation.get("weak_areas", ""))
                st.write("**Red flags:**", evaluation.get("red_flags", ""))
            else:
                st.info("Not scored yet.")

        st.divider()
        if st.button("Generate tailored materials", disabled=job.get("opportunity_type", "job") != "job"):
            if not profile:
                st.error("Create your profile first.")
            else:
                if not evaluation:
                    evaluation = score_job(profile, job, user_id=current_user_id)
                    save_evaluation(job_id, evaluation, current_user_id)
                materials = generate_materials(profile, job, evaluation, user_id=current_user_id)
                save_materials(job_id, materials, current_user_id)
                st.success("Generated materials saved. Edit before using.")
                st.rerun()

        with st.form("materials_form"):
            professional_summary = st.text_area("Customized professional summary", value=materials.get("professional_summary", ""), height=100)
            cover_letter = st.text_area("Tailored cover letter", value=materials.get("cover_letter", ""), height=260)
            resume_bullets = st.text_area("Suggested resume bullet improvements", value=materials.get("resume_bullets", ""), height=140)
            screening_answers = st.text_area("Common screening answers", value=materials.get("screening_answers", ""), height=160)
            linkedin_message = st.text_area("Short LinkedIn/recruiter message", value=materials.get("linkedin_message", ""), height=100)
            why_fit = st.text_area("Concise why I’m a fit paragraph", value=materials.get("why_fit", ""), height=100)
            status = st.selectbox("Status", STATUSES, index=STATUSES.index(next((j.get("status") for j in jobs if j["id"] == job_id), "New")))
            notes = st.text_area("Notes", value=next((j.get("notes") or "" for j in jobs if j["id"] == job_id), ""), height=90)
            if st.form_submit_button("Save edits/status"):
                save_materials(job_id, locals(), current_user_id)
                update_status(job_id, status, notes, current_user_id)
                st.success("Saved.")

elif page == "Reminders":
    st.header("7. Notifications / reminders")
    jobs = list_jobs(current_user_id)
    if jobs:
        labels = {f"#{j['id']} - {j['title']} @ {j.get('company','')}": j["id"] for j in jobs}
        with st.form("new_reminder"):
            selected = st.selectbox("Opportunity", list(labels.keys()))
            kind = st.selectbox("Reminder kind", ["High-match review", "Follow-up", "Recruiter reply", "Interview", "Deadline", "Registration deadline", "Event date"])
            date = st.date_input("Date", value=datetime.now(timezone.utc).date() + timedelta(days=3))
            time = st.time_input("Time", value=datetime.now().time().replace(second=0, microsecond=0))
            note = st.text_input("Note")
            if st.form_submit_button("Create reminder"):
                remind_at = datetime.combine(date, time).replace(tzinfo=timezone.utc).isoformat(timespec="seconds")
                create_reminder(labels[selected], kind, remind_at, note, current_user_id)
                st.success("Reminder saved locally. It appears in this app when due.")
    st.subheader("Due reminders")
    due = due_reminders(current_user_id)
    if due:
        st.dataframe(pd.DataFrame(due), use_container_width=True, hide_index=True)
    else:
        st.info("No due reminders.")

elif page == "Privacy":
    st.header("9. Privacy and security")

    st.info(
        """
        This app is currently in demo phase. Your saved profile, opportunities, evaluations,
        generated materials, statuses, notes, and reminders are connected to your signed-in account.
        """
    )

    st.success(
        """
        Your data is user-specific. When you delete stored data from this page, the app removes
        data for the currently signed-in user only.
        """
    )

    st.write(
        """
        Data is stored in SQLite for local deployments. API keys and sensitive integration settings
        are encrypted at rest with the application encryption key. In production, serve the app only
        over HTTPS so credentials are encrypted in transit too.
        """
    )

    st.write(
        """
        The app never submits applications, never clicks apply buttons, never logs into LinkedIn,
        and never scrapes private pages.
        """
    )

    st.warning(
        """
        Danger zone: this will delete your local profile, jobs, evaluations, generated materials,
        statuses, notes, and reminders for this signed-in account.
        """
    )

    confirm_delete = st.checkbox(
        "I understand this will delete my stored data for the current user only."
    )

    if st.button("Delete my stored data", disabled=not confirm_delete):
        delete_all_data(current_user_id)
        st.success("Your app data was deleted completely from our database.")
