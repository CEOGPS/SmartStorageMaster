from pathlib import Path

from app.db import connection
from app.db.models import Base, File
from app.services.scan_service import ScanService, normalize_scan_path


def test_normalize_bare_drive():
    assert str(normalize_scan_path("D:")) == "D:\\"
    assert str(normalize_scan_path(Path("c:"))) == "c:\\"
    assert str(normalize_scan_path("/tmp/x")) == "/tmp/x"


def test_rescan_updates_instead_of_duplicating(tmp_path):
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    db = connection.get_session()
    svc = ScanService(db, compute_hashes=False)
    svc.start_scan(tmp_path)
    svc.start_scan(tmp_path)  # previously collided on files.path
    assert db.query(File).count() == 2
    db.close()
