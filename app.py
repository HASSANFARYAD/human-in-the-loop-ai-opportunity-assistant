from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from job_assistant.auth import authenticate_user, public_user, register_user
from job_assistant.db import (
    OPPORTUNITY_TYPES,
    STATUSES,
    create_reminder,
    delete_all_data,
    due_reminders,
    get_evaluation,
    get_job,
    get_materials,
    get_profile,
    init_db,
    insert_job,
    list_jobs,
    save_evaluation,
    save_materials,
    update_status,
    upsert_profile,
)
from job_assistant.services.generation import generate_materials
from job_assistant.services.gmail_ingest import fetch_job_alert_messages
from job_assistant.services.parsing import extract_job_from_text, jobs_from_csv, read_uploaded_cv
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

st.set_page_config(page_title="Human-in-the-loop Opportunity Assistant", layout="wide")
st.title("Human-in-the-loop AI Opportunity Assistant")
st.caption("Track jobs, competitions, hackathons, and webinars. Safe by design: no scraping, no auto-apply, no automatic submit clicks.")


def require_streamlit_user() -> dict:
    if st.session_state.get("user"):
        return st.session_state["user"]

    st.subheader("Sign in")
    login_tab, register_tab = st.tabs(["Login", "Register"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                user = authenticate_user(email, password)
                if user:
                    st.session_state["user"] = public_user(user)
                    st.rerun()
                st.error("Invalid email or password.")
    with register_tab:
        with st.form("register_form"):
            full_name = st.text_input("Full name")
            email = st.text_input("Email", key="register_email")
            password = st.text_input("Password", type="password", key="register_password")
            if st.form_submit_button("Create account"):
                if len(password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    try:
                        user = register_user(email, password, full_name)
                        st.session_state["user"] = public_user(user)
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
    st.stop()


current_user = require_streamlit_user()
current_user_id = int(current_user["id"])

with st.sidebar:
    st.write(f"**Signed in:** {current_user['email']}")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    page = st.radio("Navigate", ["Profile", "Ingest Opportunities", "Review Queue", "Opportunity Detail", "Reminders", "Privacy"])
    st.divider()
    st.write("**Automatic import**")
    st.caption("Automatic import reads Gmail alerts only. It does not search LinkedIn or private sites.")
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
    st.caption("Status: running" if st.session_state.get("scheduler_started") else "Status: manual")
    st.divider()
    st.write("**Allowed workflow**")
    st.write("Process alerts, pasted descriptions, public/manual URLs, CSVs, and optional Gmail read-only messages.")
    st.write("For LinkedIn: open the URL yourself, review, and apply manually.")

reminders = due_reminders(current_user_id)
if reminders:
    st.warning(f"You have {len(reminders)} due reminder(s). Open Reminders to review them.")

if page == "Profile":
    st.header("1. User profile setup")
    profile = get_profile(current_user_id)
    uploaded_cv = st.file_uploader("Upload CV/resume (.pdf, .docx, .txt)", type=["pdf", "docx", "txt"])
    cv_text = profile.get("cv_text", "")
    if uploaded_cv:
        cv_text = read_uploaded_cv(uploaded_cv)
        st.success("CV text extracted. Review/edit below before saving.")
    with st.form("profile_form"):
        cv_text = st.text_area("CV / resume text", value=cv_text, height=220)
        target_roles = st.text_input("Target roles", value=profile.get("target_roles", ""))
        industries = st.text_input("Target industries", value=profile.get("industries", ""))
        locations = st.text_input("Locations", value=profile.get("locations", ""))
        remote_preference = st.text_input("Remote preference", value=profile.get("remote_preference", ""))
        salary_expectations = st.text_input("Salary expectations", value=profile.get("salary_expectations", ""))
        work_authorization = st.text_input("Visa/work authorization", value=profile.get("work_authorization", ""))
        years_experience = st.text_input("Years of experience", value=profile.get("years_experience", ""))
        skills = st.text_area("Skills", value=profile.get("skills", ""), height=90)
        deal_breakers = st.text_area("Deal-breakers", value=profile.get("deal_breakers", ""), height=90)
        if st.form_submit_button("Save profile"):
            upsert_profile(locals(), current_user_id)
            st.success("Profile saved locally.")

elif page == "Ingest Opportunities":
    st.header("2. Opportunity source ingestion")
    source_tab, public_tab, csv_tab, gmail_tab = st.tabs(["Manual / pasted", "Public discovery", "CSV upload", "Gmail read-only"])

    with source_tab:
        st.subheader("Manual URL or pasted opportunity text")
        opportunity_type = st.selectbox("Opportunity type", OPPORTUNITY_TYPES, index=0)
        source = st.selectbox("Source", ["Manual", "LinkedIn email/paste", "Indeed", "Company career page", "Recruiter", "Devpost", "Eventbrite", "Meetup", "Other"])
        raw = st.text_area("Paste opportunity URL, email, or description", height=260)
        if st.button("Extract and save opportunity", disabled=not raw.strip()):
            job = extract_job_from_text(raw, source=source, opportunity_type=opportunity_type)
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
        st.write("Use this after adding Google OAuth files. Fetch now imports matching Gmail alerts once; Start in the sidebar runs the same kind of import every 30 minutes.")
        gmail_opportunity_type = st.selectbox("Classify Gmail results as", ["auto", *OPPORTUNITY_TYPES], index=0)
        query = st.text_input("Gmail search query", value='("job alert" OR "new jobs" OR recruiter OR "is hiring" OR hackathon OR webinar OR competition OR contest OR challenge) newer_than:30d')
        max_results = st.slider("Max emails", 1, 50, 10)
        if st.button("Fetch Gmail alerts"):
            try:
                messages = fetch_job_alert_messages(query=query, max_results=max_results)
                count = 0
                for m in messages:
                    job = extract_job_from_text(
                        f"Subject: {m['subject']}\nFrom: {m['from']}\n\n{m['body']}",
                        source="Gmail",
                        opportunity_type=gmail_opportunity_type,
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
        st.dataframe(df[[c for c in visible_cols if c in df.columns]], use_container_width=True, hide_index=True)
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
                            evaluation = score_job(profile, row)
                            save_evaluation(row["id"], evaluation, current_user_id)
                            n += 1
                    st.success(f"Scored {n} opportunity/opportunities.")
                    st.rerun()
        with col2:
            st.write("Open Opportunity Detail to generate/edit materials and change status.")

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

        with col2:
            st.subheader("Evaluation")
            if st.button("Score / rescore opportunity"):
                if not profile:
                    st.error("Create your profile first.")
                else:
                    evaluation = score_job(profile, job)
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
                    evaluation = score_job(profile, job)
                    save_evaluation(job_id, evaluation, current_user_id)
                materials = generate_materials(profile, job, evaluation)
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
    st.write("Data is stored in your local SQLite database. API keys and OAuth credentials are loaded from environment variables or local files and should not be committed to git.")
    st.write("The app never submits applications, never clicks apply buttons, never logs into LinkedIn, and never scrapes private pages.")
    st.warning("Danger zone: delete all local profile, jobs, evaluations, materials, statuses, and reminders.")
    if st.button("Delete my stored data"):
        delete_all_data(current_user_id)
        st.success("Your local app data was deleted.")
