import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes.agent_routes import _execute_tool
from app.db import connection
from app.db.models import Base, File, ScanSession
from app.main import create_app
from app.services.cleanup_service import CleanupService
from app.services.journal_service import JournalService
from app.services.organizer_service import OrganizerService
from app.services.protection_service import ProtectedPathError, ProtectionService, _within
from app.services.rename_service import RenameService
from app.services.sort_service import SortService

posix_only = pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX system paths")


@pytest.fixture
def db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    s = connection.get_session()
    yield s
    s.close()


def add_file(db, path: Path, data="x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    scan = db.query(ScanSession).first()
    if scan is None:
        scan = ScanSession(start_path=str(path.parent), status="completed")
        db.add(scan)
        db.flush()
    rec = File(path=str(path), name=path.name, size=len(data), scan_id=scan.id)
    db.add(rec)
    db.commit()
    return rec


def protect(db, folder: Path, note=None):
    ProtectionService(db).add(str(folder), note)


# ---- the rule itself -------------------------------------------------------
def test_within_does_not_match_sibling_with_same_prefix():
    sep = os.sep
    assert _within(sep + "a" + sep + "b" + sep + "c", sep + "a" + sep + "b")
    assert _within(sep + "a" + sep + "b", sep + "a" + sep + "b")
    assert not _within(sep + "a" + sep + "b2" + sep + "c", sep + "a" + sep + "b")


@posix_only
def test_system_folders_are_protected_and_normal_ones_are_not(db, tmp_path):
    prot = ProtectionService(db)
    assert prot.blocked_reason("/etc/hosts") and prot.blocked_reason("/usr/bin/python3")
    assert prot.blocked_reason("/etc/../etc/hosts")             # path tricks do not help
    assert prot.blocked_reason(tmp_path / "file.txt") is None


def test_credential_folders_in_home_are_protected(db, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert ProtectionService(db).blocked_reason(tmp_path / ".ssh" / "id_rsa")
    assert ProtectionService(db).blocked_reason(tmp_path / "Documents" / "a.txt") is None


def test_user_folder_protects_it_and_everything_inside_but_not_siblings(db, tmp_path):
    protect(db, tmp_path / "Taxes", "never touch")
    prot = ProtectionService(db)
    assert "never touch" in prot.blocked_reason(tmp_path / "Taxes" / "2024" / "a.pdf")
    assert prot.blocked_reason(tmp_path / "Taxes2" / "a.pdf") is None
    assert prot.blocked_reason(tmp_path / "Other" / "a.pdf") is None


def test_symlink_into_a_protected_folder_does_not_bypass_protection(db, tmp_path):
    secret = tmp_path / "Secret"
    secret.mkdir()
    (secret / "k.txt").write_text("k")
    protect(db, secret)
    link = tmp_path / "innocent"
    try:
        link.symlink_to(secret, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert ProtectionService(db).blocked_reason(link / "k.txt")


def test_adding_is_idempotent_and_validates(db, tmp_path):
    svc = ProtectionService(db)
    first = svc.add(str(tmp_path / "A"))
    again = svc.add(str(tmp_path / "A"))
    assert again["already"] and again["id"] == first["id"]
    with pytest.raises(ValueError):
        svc.add("relative/path")
    with pytest.raises(ValueError):
        svc.add("   ")
    assert svc.remove(first["id"]) and not svc.remove(first["id"])


# ---- every operation refuses protected files -------------------------------
def test_move_refuses_protected_files_and_protected_destinations(db, tmp_path):
    keep = add_file(db, tmp_path / "Taxes" / "a.txt")
    free = add_file(db, tmp_path / "Free" / "b.txt")
    protect(db, tmp_path / "Taxes")
    result = OrganizerService(db).move_files([keep.id, free.id], str(tmp_path / "out"))
    assert result["moved"] == 1 and result["failed"] == 1 and len(result["blocked"]) == 1
    assert (tmp_path / "Taxes" / "a.txt").exists() and (tmp_path / "out" / "b.txt").exists()
    with pytest.raises(ProtectedPathError):
        OrganizerService(db).move_files([free.id], str(tmp_path / "Taxes" / "inbox"))
    assert not (tmp_path / "Taxes" / "inbox").exists()


def test_delete_and_backup_refuse_protected_files(db, tmp_path):
    keep = add_file(db, tmp_path / "Taxes" / "a.txt")
    gone = add_file(db, tmp_path / "Junk" / "b.txt")
    protect(db, tmp_path / "Taxes")
    result = OrganizerService(db).delete_files_with_backup([keep.id, gone.id])
    assert (tmp_path / "Taxes" / "a.txt").exists() and not (tmp_path / "Junk" / "b.txt").exists()
    assert result["deleted"] == 1 and len(result["blocked"]) == 1
    assert CleanupService(db).backup_files([keep.id])["backed_up"] == 0


def test_ai_assistant_tool_cannot_delete_protected_files(db, tmp_path):
    keep = add_file(db, tmp_path / "Taxes" / "a.txt")
    protect(db, tmp_path / "Taxes")
    result = _execute_tool("delete_files", {"file_ids": [keep.id]}, db)
    assert result["deleted"] == 0 and len(result["blocked"]) == 1
    assert (tmp_path / "Taxes" / "a.txt").exists()
    result = _execute_tool("backup_files", {"file_ids": [keep.id]}, db)
    assert result["backed_up"] == 0


def test_empty_folder_cleanup_skips_protected_empty_folders(db, tmp_path):
    (tmp_path / "Root" / "Taxes").mkdir(parents=True)
    (tmp_path / "Root" / "Empty").mkdir()
    protect(db, tmp_path / "Root" / "Taxes")
    result = OrganizerService(db).delete_empty_folders(str(tmp_path / "Root"))
    assert (tmp_path / "Root" / "Taxes").exists() and not (tmp_path / "Root" / "Empty").exists()
    assert result["count"] == 1


def test_creating_a_folder_inside_a_protected_one_is_refused(db, tmp_path):
    protect(db, tmp_path / "Taxes")
    with pytest.raises(ProtectedPathError):
        OrganizerService(db).create_folder(str(tmp_path / "Taxes" / "new"))
    assert not (tmp_path / "Taxes" / "new").exists()


def test_sort_skips_protected_files_and_refuses_protected_destination(db, tmp_path):
    add_file(db, tmp_path / "Mix" / "a.jpg")
    protect(db, tmp_path / "Mix" / "Locked")
    add_file(db, tmp_path / "Mix" / "Locked" / "b.jpg")
    plan = SortService(db).plan(str(tmp_path / "Mix"), "extension", recursive=True)
    assert plan["total"] == 1 and plan["protected"] == 1
    SortService(db).apply(str(tmp_path / "Mix"), "extension", recursive=True)
    assert (tmp_path / "Mix" / "Locked" / "b.jpg").exists()
    with pytest.raises(ProtectedPathError):
        SortService(db).plan(str(tmp_path / "Mix" / "Locked"), "type")
    with pytest.raises(ProtectedPathError):
        SortService(db).plan(str(tmp_path / "Mix"), "type", destination=str(tmp_path / "Mix" / "Locked"))


def test_rename_marks_protected_files_and_never_renames_them(db, tmp_path):
    add_file(db, tmp_path / "Mix" / "a.txt")
    protect(db, tmp_path / "Mix" / "Locked")
    add_file(db, tmp_path / "Mix" / "Locked" / "b.txt")
    svc = RenameService(db)
    plan = svc.plan(folder=str(tmp_path / "Mix"), recursive=True, template="x_{name}")
    assert plan["counts"]["protected"] == 1 and plan["counts"]["ok"] == 1
    assert {i["status"] for i in plan["items"]} == {"ok", "protected"}
    result = svc.apply(folder=str(tmp_path / "Mix"), recursive=True, template="x_{name}")
    assert result["renamed"] == 1 and result["skipped"] == 1
    assert (tmp_path / "Mix" / "Locked" / "b.txt").exists() and (tmp_path / "Mix" / "x_a.txt").exists()


def test_undo_will_not_move_files_into_or_out_of_a_folder_protected_since(db, tmp_path):
    rec = add_file(db, tmp_path / "A" / "a.txt")
    moved = OrganizerService(db).move_files([rec.id], str(tmp_path / "B"))
    protect(db, tmp_path / "A")                                   # original home became protected
    undo = JournalService(db).undo(moved["operation_id"])
    assert undo["restored"] == 0 and not undo["fully_undone"] and undo["skipped"]
    assert (tmp_path / "B" / "a.txt").exists() and not (tmp_path / "A" / "a.txt").exists()


# ---- HTTP -------------------------------------------------------------------
def test_api_manage_list_and_http_status_codes(tmp_path):
    with TestClient(create_app("testing")) as c:
        listing = c.get("/api/protection").json()["data"]
        assert listing["system"] and listing["user"] == []
        r = c.post("/api/protection", json={"path": str(tmp_path / "Taxes"), "note": "taxes"})
        pid = r.json()["data"]["id"]
        assert c.get("/api/protection").json()["data"]["user"][0]["note"] == "taxes"
        assert c.post("/api/protection", json={"path": "relative"}).status_code == 400

        (tmp_path / "Taxes").mkdir()
        assert c.post("/api/organizer/create-folder", json={"path": str(tmp_path / "Taxes" / "x")}).status_code == 403
        assert c.post("/api/organizer/move", json={"file_ids": [], "destination": str(tmp_path / "Taxes")}).status_code == 403
        assert c.post("/api/organizer/sort/preview", json={"source": str(tmp_path / "Taxes"), "mode": "type"}).status_code == 403
        assert c.post("/api/organizer/delete-empty-folders", json={"root": str(tmp_path / "Taxes")}).status_code == 403

        assert c.delete(f"/api/protection/{pid}").status_code == 200
        assert c.delete(f"/api/protection/{pid}").status_code == 404
        assert c.post("/api/organizer/create-folder", json={"path": str(tmp_path / "Taxes" / "x")}).status_code == 200


def test_blocked_move_does_not_leave_an_empty_destination_folder_behind(db, tmp_path):
    keep = add_file(db, tmp_path / "Taxes" / "a.txt")
    protect(db, tmp_path / "Taxes")
    result = OrganizerService(db).move_files([keep.id], str(tmp_path / "Elsewhere"))
    assert result["moved"] == 0 and len(result["blocked"]) == 1
    assert not (tmp_path / "Elsewhere").exists()
    # and a move with create_if_missing=False into a missing folder still fails cleanly
    other = add_file(db, tmp_path / "Free" / "b.txt")
    result = OrganizerService(db).move_files([other.id], str(tmp_path / "Nope"), create_if_missing=False)
    assert result["moved"] == 0 and (tmp_path / "Free" / "b.txt").exists() and not (tmp_path / "Nope").exists()
