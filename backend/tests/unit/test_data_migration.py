"""
ADR-005: AppData migration, backup and staged restore.

Every test points MIRRORHUB_DATA_DIR at a temp dir; the real %APPDATA% is never touched.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from app.core import data_migration as dm
from app.core import runtime_paths as rp


@pytest.fixture()
def dirs(tmp_path, monkeypatch):
    data = tmp_path / "data"
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    monkeypatch.setenv("MIRRORHUB_DATA_DIR", str(data))
    return data, legacy


def make_db(path: Path, rows=("a", "b")):
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE t (v TEXT)")
    c.executemany("INSERT INTO t VALUES (?)", [(r,) for r in rows])
    c.commit()
    c.close()


def read_rows(path: Path):
    c = sqlite3.connect(str(path))
    try:
        return [r[0] for r in c.execute("SELECT v FROM t ORDER BY v")]
    finally:
        c.close()


def test_data_dir_follows_env(dirs):
    data, _ = dirs
    assert rp.data_dir() == data
    assert rp.db_path() == data / "mirrorhub.db"
    assert rp.uploads_dir().is_dir() and rp.logs_dir().is_dir() and rp.backups_dir().is_dir()


def test_default_data_dir_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.delenv("MIRRORHUB_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert rp.data_dir() == tmp_path / "Mirrorhub"


def test_install_root_override(monkeypatch, tmp_path):
    monkeypatch.setenv("MIRRORHUB_INSTALL_ROOT", str(tmp_path))
    assert rp.install_root() == tmp_path
    assert rp.tools_root() == tmp_path / "tools"


def test_migration_copies_and_never_touches_legacy(dirs):
    data, legacy = dirs
    make_db(legacy / "mirrorhub.db")
    (legacy / "uploads").mkdir()
    (legacy / "uploads" / "x.txt").write_text("hello")
    before = (legacy / "mirrorhub.db").read_bytes()

    rep = dm.migrate_legacy_data(legacy)

    assert rep["status"] == "migrated"
    assert read_rows(rp.db_path()) == ["a", "b"]
    assert (legacy / "mirrorhub.db").read_bytes() == before            # untouched
    assert (legacy / "uploads" / "x.txt").exists()                      # untouched
    assert (rp.uploads_dir() / "x.txt").read_text() == "hello"
    assert Path(rep["backup"]).exists()                                 # rollback copy
    assert (data / dm.MIGRATION_MARKER).exists()


def test_migration_is_idempotent_and_does_not_overwrite(dirs):
    data, legacy = dirs
    make_db(legacy / "mirrorhub.db", ("legacy",))
    dm.migrate_legacy_data(legacy)
    # user keeps working in the new DB
    c = sqlite3.connect(str(rp.db_path()))
    c.execute("INSERT INTO t VALUES ('new')")
    c.commit()
    c.close()
    rep = dm.migrate_legacy_data(legacy)
    assert rep["status"] == "skipped"
    assert read_rows(rp.db_path()) == ["legacy", "new"]


def test_existing_new_db_is_not_replaced(dirs):
    data, legacy = dirs
    make_db(legacy / "mirrorhub.db", ("legacy",))
    data.mkdir(parents=True, exist_ok=True)
    make_db(rp.db_path(), ("keep",))
    rep = dm.migrate_legacy_data(legacy)
    assert rep["status"] == "skipped"
    assert read_rows(rp.db_path()) == ["keep"]


def test_corrupt_legacy_db_is_not_copied(dirs):
    _, legacy = dirs
    (legacy / "mirrorhub.db").write_bytes(b"this is not sqlite" * 50)
    rep = dm.migrate_legacy_data(legacy)
    assert rep["status"] == "failed"
    assert not rp.db_path().exists()
    assert (legacy / "mirrorhub.db").exists()


def test_fresh_install_without_legacy(dirs):
    _, legacy = dirs
    rep = dm.migrate_legacy_data(legacy)
    assert rep["status"] == "fresh"


def test_backup_list_and_name_validation(dirs):
    make_db(rp.db_path())
    b = dm.create_backup("my label!!")
    assert b.exists() and "mylabel" in b.name
    names = [x["name"] for x in dm.list_backups()]
    assert b.name in names
    for bad in ("../x.db", "a/b.db", "notdb.txt", "", "..\\evil.db"):
        with pytest.raises(dm.DataError):
            dm.stage_restore(bad)


def test_backup_without_db_raises(dirs):
    with pytest.raises(dm.DataError):
        dm.create_backup()


def test_staged_restore_applies_at_startup_with_safety_backup(dirs):
    make_db(rp.db_path(), ("v1",))
    good = dm.create_backup("good")
    c = sqlite3.connect(str(rp.db_path()))
    c.execute("INSERT INTO t VALUES ('v2')")
    c.commit()
    c.close()

    dm.stage_restore(good.name)
    assert read_rows(rp.db_path()) == ["v1", "v2"]          # nothing happens until restart
    res = dm.apply_pending_restore()

    assert res["restored"] == good.name
    assert read_rows(rp.db_path()) == ["v1"]
    safety = Path(res["safety_backup"])
    assert read_rows(safety) == ["v1", "v2"]                # the state before restore is recoverable
    assert dm.apply_pending_restore() is None               # flag consumed


def test_corrupt_backup_cannot_be_staged(dirs):
    make_db(rp.db_path())
    bad = rp.backups_dir() / "broken.db"
    bad.write_bytes(b"garbage" * 100)
    with pytest.raises(dm.DataError):
        dm.stage_restore("broken.db")


def test_cancel_staged_restore(dirs):
    make_db(rp.db_path())
    b = dm.create_backup()
    dm.stage_restore(b.name)
    assert dm.cancel_staged_restore() is True
    assert dm.cancel_staged_restore() is False
    assert dm.apply_pending_restore() is None


def test_failed_restore_keeps_running_and_flag(dirs):
    make_db(rp.db_path(), ("v1",))
    flag = rp.data_dir() / dm.PENDING_RESTORE
    flag.write_text(json.dumps({"name": "missing.db"}))
    res = dm.apply_pending_restore()
    assert "error" in res
    assert flag.exists()
    assert read_rows(rp.db_path()) == ["v1"]


def test_sqlite_copy_refuses_overwrite(dirs, tmp_path):
    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    make_db(a)
    make_db(b)
    with pytest.raises(dm.DataError):
        dm.sqlite_copy(a, b)
