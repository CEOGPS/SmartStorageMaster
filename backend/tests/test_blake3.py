import blake3
import pytest
from sqlalchemy import create_engine, inspect, text

from app.core import scanner as scanner_mod
from app.core.scanner import FileScanner
from app.db import connection
from app.db.connection import add_missing_columns
from app.db.models import Base, File, ScanSession
from app.services.duplicate_service import DuplicateService
from app.services.scan_service import ScanService


@pytest.fixture
def db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    s = connection.get_session()
    yield s
    s.close()


def scan(db, folder):
    svc = ScanService(db)
    return svc.start_scan(folder)


def groups(db, scan_id):
    svc = DuplicateService(db)
    return svc.detect_exact_duplicates(scan_id)


def test_hash_matches_reference_blake3_including_empty_and_large_files(tmp_path):
    (tmp_path / "empty").write_bytes(b"")
    (tmp_path / "small").write_bytes(b"hello world")
    big = bytes(range(256)) * 20000  # ~5 MB, exercises the mmap path
    (tmp_path / "big").write_bytes(big)
    hashes = {m.name: m.hash_blake3 for m in FileScanner(compute_hashes=True).scan(tmp_path, recursive=False)}
    assert hashes["empty"] == blake3.blake3(b"").hexdigest()
    assert hashes["small"] == blake3.blake3(b"hello world").hexdigest()
    assert hashes["big"] == blake3.blake3(big).hexdigest()


def test_hashing_can_be_turned_off(tmp_path):
    (tmp_path / "a").write_bytes(b"x")
    m = next(iter(FileScanner(compute_hashes=False).scan(tmp_path, recursive=False)))
    assert m.hash_blake3 is None and m.hash_md5 is None


def test_exact_duplicates_are_grouped_by_blake3(db, tmp_path):
    (tmp_path / "a.txt").write_text("same content")
    (tmp_path / "b.txt").write_text("same content")
    (tmp_path / "c.txt").write_text("different")
    sid = scan(db, tmp_path)
    assert len(groups(db, sid)) == 1
    # c.txt has a size no other file shares, so it cannot be a duplicate and is not read
    names = {f.name for f in db.query(File).filter(File.hash_blake3.isnot(None))}
    assert names == {"a.txt", "b.txt"}


def test_same_hash_but_different_size_is_never_grouped(db, tmp_path):
    scan_row = ScanSession(start_path=str(tmp_path), status="completed")
    db.add(scan_row)
    db.flush()
    for n, size in (("x", 10), ("y", 11)):
        db.add(File(path=str(tmp_path / n), name=n, size=size, scan_id=scan_row.id, hash_blake3="ab" * 32))
    db.commit()
    assert groups(db, scan_row.id) == []


def test_old_rows_with_only_md5_still_group_and_are_not_mixed_with_blake3(db, tmp_path):
    scan_row = ScanSession(start_path=str(tmp_path), status="completed")
    db.add(scan_row)
    db.flush()
    rows = [("o1", "md5hash", None), ("o2", "md5hash", None),      # old scan: md5 only
            ("n1", None, "b3hash"), ("n2", None, "b3hash"),        # new scan: blake3 only
            ("lone", "md5hash", "b3other")]                        # has blake3, so md5 is ignored
    for n, md5, b3 in rows:
        db.add(File(path=str(tmp_path / n), name=n, size=5, scan_id=scan_row.id, hash_md5=md5, hash_blake3=b3))
    db.commit()
    assert len(groups(db, scan_row.id)) == 2


def test_falls_back_to_md5_when_blake3_is_not_installed(db, tmp_path, monkeypatch):
    monkeypatch.setattr(scanner_mod, "_blake3", None)
    (tmp_path / "a.txt").write_text("dup")
    (tmp_path / "b.txt").write_text("dup")
    sid = scan(db, tmp_path)
    rec = db.query(File).first()
    assert rec.hash_blake3 is None and rec.hash_md5
    assert len(groups(db, sid)) == 1


def test_unreadable_file_gives_no_hash_instead_of_crashing(tmp_path):
    assert FileScanner._blake3_hash(tmp_path / "does-not-exist") is None


def test_old_database_is_upgraded_in_place_and_keeps_its_data(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'old.db'}")
    with engine.begin() as c:  # a files table as it was before hash_blake3 existed
        c.execute(text("CREATE TABLE files (id VARCHAR(36) PRIMARY KEY, scan_id VARCHAR(36) NOT NULL, "
                       "path VARCHAR(2048) NOT NULL, name VARCHAR(256) NOT NULL, size INTEGER NOT NULL, hash_md5 VARCHAR(32))"))
        c.execute(text("INSERT INTO files VALUES ('1','s','/a','a',3,'abc')"))
    add_missing_columns(engine)
    add_missing_columns(engine)  # idempotent
    assert "hash_blake3" in {c["name"] for c in inspect(engine).get_columns("files")}
    with engine.connect() as c:
        assert c.execute(text("SELECT hash_md5, hash_blake3 FROM files")).one() == ("abc", None)
