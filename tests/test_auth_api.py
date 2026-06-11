from __future__ import annotations

import importlib
import sqlite3
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "auth.sqlite3"
    monkeypatch.setenv("APP_DB_PATH", str(db_path))
    from job_assistant.config import Environment, settings
    import api_server

    settings.db_path = str(db_path)
    settings.environment = Environment.DEV
    settings.database_url = None
    settings.rate_limits_enabled = False
    settings.scheduler_enabled = False
    settings.access_token_expire_minutes = 60
    settings.refresh_token_expire_days = 30
    settings.session_cookie_name = "job_assistant_refresh"
    settings.session_cookie_secure = False
    settings.session_cookie_samesite = "lax"
    settings.session_cookie_path = "/api/v1/auth"
    settings.password_reset_token_expire_minutes = 60
    settings.frontend_reset_password_url = "http://localhost:3000/reset-password"
    settings.smtp_host = ""
    settings.smtp_from_email = ""
    settings.cors_origins = "http://localhost:3000,http://localhost:3001"
    settings.cors_allow_credentials = True
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT
            );
            """
        )
    importlib.reload(api_server)
    return TestClient(api_server.app)


def test_register_rejects_invalid_email_and_weak_password(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    invalid_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "StrongPass123!", "full_name": "Test User"},
    )
    assert invalid_email.status_code == 400

    weak_password = client.post(
        "/api/v1/auth/register",
        json={"email": "person@example.com", "password": "password123", "full_name": "Test User"},
    )
    assert weak_password.status_code == 400


def test_login_sets_refresh_cookie_and_refresh_rotates_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {"email": "person@example.com", "password": "StrongerPass123!", "full_name": "Test User"}

    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 200
    assert registered.json()["access_token"]
    assert "job_assistant_refresh" in registered.cookies
    cookie_header = registered.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "samesite=lax" in cookie_header
    assert "path=/api/v1/auth" in cookie_header
    assert "secure" not in cookie_header

    old_refresh_token = registered.cookies["job_assistant_refresh"]
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]
    assert refreshed.cookies["job_assistant_refresh"] != old_refresh_token

    reuse = TestClient(client.app)
    reuse.cookies.set("job_assistant_refresh", old_refresh_token, path="/api/v1/auth")
    reused = reuse.post("/api/v1/auth/refresh")
    assert reused.status_code == 401

    logged_out = client.post("/api/v1/auth/logout")
    assert logged_out.status_code == 200
    assert "max-age=0" in logged_out.headers["set-cookie"].lower()

    refresh_after_logout = client.post("/api/v1/auth/refresh")
    assert refresh_after_logout.status_code == 401


def test_expired_access_token_recovers_via_refresh(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from job_assistant.config import settings

    settings.access_token_expire_minutes = -1
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "expired@example.com", "password": "StrongerPass123!", "full_name": "Expired User"},
    )
    assert registered.status_code == 200
    expired_access = registered.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_access}"}).status_code == 401

    settings.access_token_expire_minutes = 60
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    new_access = refreshed.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200


def test_invalid_expired_and_revoked_refresh_cookies_fail_safely(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {"email": "session@example.com", "password": "StrongerPass123!", "full_name": "Session User"}

    assert client.post("/api/v1/auth/refresh").status_code == 401
    client.cookies.set("job_assistant_refresh", "not-a-real-refresh-token", path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401

    from job_assistant.config import settings

    settings.refresh_token_expire_days = -1
    registered = client.post("/api/v1/auth/register", json=payload)
    assert registered.status_code == 200
    assert client.post("/api/v1/auth/refresh").status_code == 401


def _latest_reset_token() -> str:
    from job_assistant.email_delivery import DEV_EMAIL_OUTBOX

    reset_url = DEV_EMAIL_OUTBOX[-1]["reset_url"]
    return parse_qs(urlparse(reset_url).query)["token"][0]


def test_password_reset_flow_is_generic_hashed_single_use_and_revokes_sessions(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from job_assistant.email_delivery import DEV_EMAIL_OUTBOX

    DEV_EMAIL_OUTBOX.clear()
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "ResetUser@example.com", "password": "StrongerPass123!", "full_name": "Reset User"},
    )
    assert registered.status_code == 200
    refresh_cookie = registered.cookies["job_assistant_refresh"]

    existing = client.post("/api/v1/auth/forgot-password", json={"email": "resetuser@example.com"})
    missing = client.post("/api/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert existing.status_code == 200
    assert missing.status_code == 200
    assert existing.json() == missing.json()
    assert len(DEV_EMAIL_OUTBOX) == 1

    token = _latest_reset_token()
    with sqlite3.connect(tmp_path / "auth.sqlite3") as con:
        row = con.execute("SELECT token_hash, consumed_at FROM password_reset_tokens").fetchone()
    assert row[0] != token
    assert len(row[0]) == 64
    assert row[1] is None

    weak = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "password123"})
    assert weak.status_code == 400

    reset = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "NewStrongerPass123!"})
    assert reset.status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "resetuser@example.com", "password": "NewStrongerPass123!"}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "password": "AnotherStrongPass123!"}).status_code == 400

    stale_session = TestClient(client.app)
    stale_session.cookies.set("job_assistant_refresh", refresh_cookie, path="/api/v1/auth")
    assert stale_session.post("/api/v1/auth/refresh").status_code == 401


def test_expired_and_invalid_password_reset_tokens_fail_safely(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from job_assistant.email_delivery import DEV_EMAIL_OUTBOX

    DEV_EMAIL_OUTBOX.clear()
    assert client.post(
        "/api/v1/auth/register",
        json={"email": "expired-reset@example.com", "password": "StrongerPass123!", "full_name": "Expired Reset"},
    ).status_code == 200
    assert client.post("/api/v1/auth/forgot-password", json={"email": "expired-reset@example.com"}).status_code == 200
    token = _latest_reset_token()

    with sqlite3.connect(tmp_path / "auth.sqlite3") as con:
        con.execute("UPDATE password_reset_tokens SET expires_at='2000-01-01T00:00:00+00:00'")
        con.commit()

    expired = client.post("/api/v1/auth/reset-password", json={"token": token, "password": "NewStrongerPass123!"})
    invalid = client.post("/api/v1/auth/reset-password", json={"token": "not-a-token", "password": "NewStrongerPass123!"})
    assert expired.status_code == 400
    assert invalid.status_code == 400


def test_production_refresh_cookie_and_startup_settings_are_secure(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    from job_assistant.config import Environment, settings

    settings.environment = Environment.PROD
    settings.access_token_expire_minutes = 15
    settings.session_cookie_secure = True
    settings.session_cookie_samesite = "strict"
    settings.session_cookie_path = "/api/v1/auth"
    settings.cors_origins = "https://app.example.com"
    settings.cors_allow_credentials = True
    settings.jwt_secret_key = "x" * 40
    settings.app_encryption_key = "configured"
    settings.database_url = "postgresql://user:pass@db/job_assistant"
    settings.rate_limits_enabled = False
    settings.smtp_host = "smtp.example.com"
    settings.smtp_from_email = "no-reply@example.com"

    registered = client.post(
        "/api/v1/auth/register",
        json={"email": "prod@example.com", "password": "StrongerPass123!", "full_name": "Prod User"},
    )
    assert registered.status_code == 200
    cookie_header = registered.headers["set-cookie"].lower()
    assert "httponly" in cookie_header
    assert "secure" in cookie_header
    assert "samesite=strict" in cookie_header
    assert settings.startup_warnings() == []

    settings.cors_origins = "*"
    assert any("wildcard" in warning.lower() for warning in settings.startup_warnings())


def test_frontend_auth_client_retries_once_without_localstorage_primary_store():
    source = open("frontend/src/services/client.ts", encoding="utf-8").read()

    assert "let accessToken: string | null = null" in source
    assert "window.localStorage.getItem" not in source
    assert "refreshPromise" in source
    assert "!originalRequest._retry" in source
    assert "originalRequest._retry = true" in source
    assert "return apiClient(originalRequest)" in source


def test_frontend_auth_service_includes_password_reset_endpoints():
    source = open("frontend/src/services/auth.service.ts", encoding="utf-8").read()

    assert '"/auth/forgot-password"' in source
    assert '"/auth/reset-password"' in source
