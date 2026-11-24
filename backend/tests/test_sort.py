from datetime import datetime

import pytest

from app.db import connection
from app.db.models import Base, File, ScanSession
from app.services.journal_service import JournalService
from app.services.sort_service import SortService


@pytest.fixture
def db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    session = connection.get_session()
    yield session
    session.close()


def _add(db, folder, name, when=datetime(2024, 3, 5), mime=None):
    p = folder / name
    p.write_text(name)
    scan = db.query(ScanSession).first()
    if scan is None:
        scan = ScanSession(start_path=str(folder), status="completed")
        db.add(scan)
        db.flush()
    rec = File(path=str(p), name=name, size=1, scan_id=scan.id, modified_at=when, mime_type=mime)
    db.add(rec)
    db.commit()
    return p


def test_preview_changes_nothing(db, tmp_path):
    a = _add(db, tmp_path, "a.jpg")
    plan = SortService(db).plan(str(tmp_path), "extension")
    assert plan["total"] == 1 and plan["folders"] == {"jpg": 1}
    assert a.exists() and not (tmp_path / "jpg").exists()


def test_sort_by_type_extension_and_date(db, tmp_path):
    _add(db, tmp_path, "a.jpg", mime="image/jpeg")
    _add(db, tmp_path, "b.pdf", when=datetime(2023, 12, 1))
    _add(db, tmp_path, "noext")
    svc = SortService(db)
    assert svc.plan(str(tmp_path), "type")["folders"] == {"Image": 1, "Document": 1, "Other": 1}
    assert svc.plan(str(tmp_path), "extension")["folders"] == {"jpg": 1, "pdf": 1, "no-extension": 1}
    assert svc.plan(str(tmp_path), "date", "month")["folders"] == {"2024-03": 2, "2023-12": 1}


def test_apply_moves_updates_db_and_undo_restores(db, tmp_path):
    a = _add(db, tmp_path, "a.jpg")
    result = SortService(db).apply(str(tmp_path), "extension")
    assert result["moved"] == 1 and not a.exists()
    assert (tmp_path / "jpg" / "a.jpg").exists()
    assert db.query(File).one().path == str(tmp_path / "jpg" / "a.jpg")

    JournalService(db).undo(result["operation_id"])
    assert a.exists() and not (tmp_path / "jpg" / "a.jpg").exists()


def test_name_collision_gets_suffix_not_overwrite(db, tmp_path):
    (tmp_path / "jpg").mkdir()
    (tmp_path / "jpg" / "a.jpg").write_text("existing")
    _add(db, tmp_path, "a.jpg")
    SortService(db).apply(str(tmp_path), "extension")
    assert (tmp_path / "jpg" / "a.jpg").read_text() == "existing"
    assert (tmp_path / "jpg" / "a (1).jpg").exists()


def test_rerun_is_idempotent_and_bad_mode_rejected(db, tmp_path):
    _add(db, tmp_path, "a.jpg")
    svc = SortService(db)
    svc.apply(str(tmp_path), "extension")
    assert svc.plan(str(tmp_path), "extension", recursive=True)["total"] == 0
    with pytest.raises(ValueError):
        svc.plan(str(tmp_path), "bogus")


def test_stale_index_row_at_destination_does_not_break_sort_or_lose_undo(db, tmp_path):
    """Regression: a leftover index row at the destination path used to raise
    UNIQUE(files.path) after the file had already moved, losing the undo record."""
    a = _add(db, tmp_path, "a.jpg")
    scan = db.query(ScanSession).first()
    db.add(File(path=str(tmp_path / "jpg" / "a.jpg"), name="a.jpg", size=1, scan_id=scan.id))
    db.commit()  # stale row: nothing exists on disk there

    result = SortService(db).apply(str(tmp_path), "extension")
    assert result["moved"] == 1 and not result["failed"] and result["operation_id"]
    assert (tmp_path / "jpg" / "a.jpg").exists()
    assert db.query(File).count() == 1

    JournalService(db).undo(result["operation_id"])
    assert a.exists()
    assert db.query(File).one().path == str(a)
