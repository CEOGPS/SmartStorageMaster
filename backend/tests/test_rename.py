from datetime import datetime

import pytest

from app.db import connection
from app.db.models import Base, File, ScanSession
from app.services.journal_service import JournalService
from app.services.rename_service import RenameError, RenameService, validate_name


@pytest.fixture
def db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    s = connection.get_session()
    yield s
    s.close()


def add(db, folder, name, when=datetime(2024, 3, 5, 14, 30), size=2048):
    p = folder / name
    p.write_text(name)
    scan = db.query(ScanSession).first()
    if scan is None:
        scan = ScanSession(start_path=str(folder), status="completed")
        db.add(scan)
        db.flush()
    db.add(File(path=str(p), name=name, size=size, scan_id=scan.id, modified_at=when, created_at=when))
    db.commit()
    return p


def names(folder):
    return sorted(p.name for p in folder.iterdir())


def new_names(plan):
    return [i["new_name"] for i in plan["items"]]


def test_preview_does_not_touch_disk(db, tmp_path):
    add(db, tmp_path, "a.txt")
    plan = RenameService(db).plan(folder=str(tmp_path), template="x_{name}")
    assert new_names(plan) == ["x_a.txt"] and names(tmp_path) == ["a.txt"]


def test_tokens_numbering_dates_and_case(db, tmp_path):
    add(db, tmp_path, "b.JPG", when=datetime(2023, 1, 2, 3, 4, 5))
    add(db, tmp_path, "a.jpg")
    plan = RenameService(db).plan(folder=str(tmp_path), template="Trip {n:3} {date:%Y%m%d} {parent}",
                                  start=10, step=5, case="lower", ext_case="lower")
    assert new_names(plan) == [f"trip 010 20240305 {tmp_path.name.lower()}.jpg",
                               f"trip 015 20230102 {tmp_path.name.lower()}.jpg"]


def test_regex_find_replace_with_backrefs_and_literal_mode(db, tmp_path):
    add(db, tmp_path, "IMG_2024_0001.jpg")
    svc = RenameService(db)
    plan = svc.plan(folder=str(tmp_path), find=r"IMG_(\d{4})_(\d+)", replace=r"\1-photo-\2", use_regex=True)
    assert new_names(plan) == ["2024-photo-0001.jpg"]
    # literal mode: regex characters and backslashes are plain text
    plan = svc.plan(folder=str(tmp_path), find="_2024_", replace=r"\1")
    assert new_names(plan) == [r"IMG\10001.jpg"] and plan["items"][0]["status"] == "error"


def test_invalid_and_conflicting_names_are_skipped_not_applied(db, tmp_path):
    add(db, tmp_path, "a.txt")
    add(db, tmp_path, "b.txt")
    (tmp_path / "keep.txt").write_text("not indexed, must survive")
    svc = RenameService(db)
    plan = svc.plan(folder=str(tmp_path), template="same")
    assert [i["status"] for i in plan["items"]] == ["ok", "conflict"]
    plan = svc.plan(folder=str(tmp_path), template="keep", match="^a")
    assert plan["items"][0]["status"] == "conflict"
    svc.apply(folder=str(tmp_path), template="keep", match="^a")
    assert (tmp_path / "keep.txt").read_text() == "not indexed, must survive"
    assert validate_name("CON.txt") and validate_name("a:b.txt") and validate_name("end.") and not validate_name("ok.txt")


def test_renumber_chain_and_swap_work_and_undo_restores(db, tmp_path):
    for n in ("img1.jpg", "img2.jpg", "img3.jpg"):
        add(db, tmp_path, n)
    svc = RenameService(db)
    # img1->img2, img2->img3, img3->img4: every target is another batch file's current name
    result = svc.apply(folder=str(tmp_path), find=r"img(\d)", replace=r"img_\1", use_regex=True, template="{name}")
    assert result["renamed"] == 3
    result = svc.apply(folder=str(tmp_path), template="img{n}", start=2)
    assert result["renamed"] == 3 and not result["failed"]
    assert names(tmp_path) == ["img2.jpg", "img3.jpg", "img4.jpg"]
    assert (tmp_path / "img2.jpg").read_text() == "img1.jpg"  # contents follow the file
    assert sorted(f.name for f in db.query(File).all()) == ["img2.jpg", "img3.jpg", "img4.jpg"]

    undo = JournalService(db).undo(result["operation_id"])
    assert undo["fully_undone"]
    assert names(tmp_path) == ["img_1.jpg", "img_2.jpg", "img_3.jpg"]
    assert (tmp_path / "img_1.jpg").read_text() == "img1.jpg"


def test_case_only_change_and_errors(db, tmp_path):
    add(db, tmp_path, "Photo.JPG")
    svc = RenameService(db)
    result = svc.apply(folder=str(tmp_path), template="{name}", case="lower", ext_case="lower")
    assert result["renamed"] == 1 and names(tmp_path) == ["photo.jpg"]
    for bad in ({"template": "{nope}"}, {"find": "(", "use_regex": True}, {"match": "["}):
        with pytest.raises(RenameError):
            svc.plan(folder=str(tmp_path), **bad)
    with pytest.raises(RenameError):
        svc.plan(template="x")  # no folder, no files
