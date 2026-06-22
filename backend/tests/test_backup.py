from __future__ import annotations

import sqlite3
from pathlib import Path

from job_assistant import backup
from job_assistant.config import settings


def _make_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE t (id INTEGER)")
        con.execute("INSERT INTO t VALUES (1)")


def test_create_backup_produces_valid_copy(tmp_path, monkeypatch):
    db = tmp_path / "app.sqlite3"
    _make_db(db)
    monkeypatch.setattr(settings, "db_path", str(db))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))

    dest = backup.create_backup()
    assert dest.exists()
    with sqlite3.connect(dest) as con:
        assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1


def test_prune_keeps_only_retention_newest(tmp_path, monkeypatch):
    out = tmp_path / "backups"
    out.mkdir()
    # names sort chronologically; create 5 fake backups
    for stamp in ["20260101T000000Z", "20260102T000000Z", "20260103T000000Z", "20260104T000000Z", "20260105T000000Z"]:
        (out / f"job_assistant_{stamp}.sqlite3").write_text("x")
    monkeypatch.setattr(settings, "backup_dir", str(out))
    monkeypatch.setattr(settings, "backup_retention", 2)

    removed = backup.prune_old_backups()
    assert removed == 3
    remaining = sorted(p.name for p in out.glob("job_assistant_*.sqlite3"))
    assert remaining == ["job_assistant_20260104T000000Z.sqlite3", "job_assistant_20260105T000000Z.sqlite3"]


def test_prune_disabled_when_retention_zero(tmp_path, monkeypatch):
    out = tmp_path / "backups"
    out.mkdir()
    (out / "job_assistant_20260101T000000Z.sqlite3").write_text("x")
    monkeypatch.setattr(settings, "backup_dir", str(out))
    monkeypatch.setattr(settings, "backup_retention", 0)
    assert backup.prune_old_backups() == 0


def test_upload_noop_without_bucket(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "backup_s3_bucket", "")
    assert backup.upload_to_s3(tmp_path / "x.sqlite3") is False


def test_run_backup_never_raises_on_missing_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "nope.sqlite3"))
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    assert backup.run_backup() is None
