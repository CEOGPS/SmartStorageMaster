from app.db import connection
from app.db.models import Base, File, ScanSession
from app.services.organizer_service import OrganizerService
from app.services.journal_service import JournalService


def _db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    return connection.get_session()


def _file(db, path):
    scan = db.query(ScanSession).first()
    if scan is None:
        scan = ScanSession(start_path=str(path.parent), status="completed")
        db.add(scan)
        db.flush()
    f = File(path=str(path), name=path.name, size=1, scan_id=scan.id)
    db.add(f)
    db.commit()
    return f


def test_move_then_undo_restores_file_and_record(tmp_path):
    db = _db()
    src = tmp_path / "a.txt"
    src.write_text("hi")
    rec = _file(db, src)
    dest = tmp_path / "out"

    result = OrganizerService(db).move_files([rec.id], str(dest))
    assert result["moved"] == 1 and result["operation_id"]
    assert not src.exists() and (dest / "a.txt").exists()

    undo = JournalService(db).undo(result["operation_id"])
    assert undo["restored"] == 1 and undo["fully_undone"]
    assert src.read_text() == "hi"
    db.refresh(rec)
    assert rec.path == str(src)


def test_undo_never_overwrites_and_reports_skip(tmp_path):
    db = _db()
    src = tmp_path / "a.txt"
    src.write_text("original")
    rec = _file(db, src)
    result = OrganizerService(db).move_files([rec.id], str(tmp_path / "out"))
    src.write_text("someone else's new file")  # original spot now occupied

    undo = JournalService(db).undo(result["operation_id"])
    assert undo["restored"] == 0 and not undo["fully_undone"]
    assert src.read_text() == "someone else's new file"
    assert (tmp_path / "out" / "a.txt").read_text() == "original"


def test_failed_move_records_no_operation(tmp_path):
    db = _db()
    result = OrganizerService(db).move_files(["missing-id"], str(tmp_path / "out"))
    assert result["moved"] == 0 and result["operation_id"] is None
    assert JournalService(db).list_operations() == []
