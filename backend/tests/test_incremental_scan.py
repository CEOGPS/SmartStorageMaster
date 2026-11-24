import os
from pathlib import Path

import pytest
from sqlalchemy import event

from app.core.scanner import FileScanner
from app.db import connection
from app.db.models import Base, DuplicateGroup, File
from app.services.scan_service import ScanService
from app.services.usage_service import UsageService


@pytest.fixture
def db():
    connection.init_db("sqlite:///:memory:")
    Base.metadata.create_all(connection._engine)
    s = connection.get_session()
    yield s
    s.close()


@pytest.fixture
def hash_calls(monkeypatch):
    calls = []
    real = FileScanner.content_hashes.__func__

    def counting(cls, path):
        calls.append(Path(path).name)
        return real(cls, path)

    monkeypatch.setattr(FileScanner, "content_hashes", classmethod(counting))
    return calls


def make(folder, name, data):
    p = folder / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def rec(db, name):
    return db.query(File).filter_by(name=name).one()


def test_only_files_that_share_a_size_are_hashed_and_duplicates_still_found(db, tmp_path, hash_calls):
    make(tmp_path, "a.bin", b"x" * 100)
    make(tmp_path, "b.bin", b"x" * 100)            # duplicate of a
    make(tmp_path, "c.bin", b"y" * 100)            # same size, different content
    make(tmp_path, "unique.bin", b"z" * 77)        # unique size: cannot be a duplicate
    sid = ScanService(db).start_scan(tmp_path)
    assert sorted(hash_calls) == ["a.bin", "b.bin", "c.bin"]
    assert rec(db, "unique.bin").hash_blake3 is None
    groups = db.query(DuplicateGroup).filter_by(scan_id=sid, group_type="exact").all()
    assert len(groups) == 1 and groups[0].total_size == 200


def test_rescan_of_unchanged_files_reads_nothing(db, tmp_path, hash_calls):
    make(tmp_path, "a.bin", b"x" * 100)
    make(tmp_path, "b.bin", b"x" * 100)
    svc = ScanService(db)
    svc.start_scan(tmp_path)
    first = rec(db, "a.bin").hash_blake3
    hash_calls.clear()
    sid = svc.start_scan(tmp_path)
    assert hash_calls == []
    assert rec(db, "a.bin").hash_blake3 == first
    assert db.query(DuplicateGroup).filter_by(scan_id=sid, group_type="exact").count() == 1


def test_changed_file_is_rehashed_and_a_stale_hash_is_never_kept(db, tmp_path, hash_calls):
    a = make(tmp_path, "a.bin", b"x" * 100)
    make(tmp_path, "b.bin", b"x" * 100)
    svc = ScanService(db)
    svc.start_scan(tmp_path)
    old = rec(db, "a.bin").hash_blake3

    # same size, different content, newer mtime -> must be re-read, hash must change
    a.write_bytes(b"q" * 100)
    os.utime(a, (a.stat().st_atime, a.stat().st_mtime + 60))
    hash_calls.clear()
    sid = svc.start_scan(tmp_path)
    assert "a.bin" in hash_calls and rec(db, "a.bin").hash_blake3 != old
    assert db.query(DuplicateGroup).filter_by(scan_id=sid, group_type="exact").count() == 0

    # now its size becomes unique: it keeps no hash from the old content
    a.write_bytes(b"w" * 55)
    os.utime(a, (a.stat().st_atime, a.stat().st_mtime + 120))
    svc.start_scan(tmp_path)
    assert rec(db, "a.bin").hash_blake3 is None


def test_if_the_size_survey_fails_every_file_is_hashed(db, tmp_path, hash_calls, monkeypatch):
    make(tmp_path, "a.bin", b"x" * 10)
    make(tmp_path, "unique.bin", b"y" * 11)
    monkeypatch.setattr(ScanService, "_survey", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    ScanService(db).start_scan(tmp_path)
    assert sorted(hash_calls) == ["a.bin", "unique.bin"]


def test_old_md5_only_rows_are_rehashed_so_hash_types_never_mix(db, tmp_path, hash_calls):
    a = make(tmp_path, "a.bin", b"x" * 100)
    b = make(tmp_path, "b.bin", b"x" * 100)
    svc = ScanService(db)
    svc.start_scan(tmp_path)
    for r in db.query(File).all():       # simulate rows from before BLAKE3 existed
        r.hash_md5, r.hash_blake3 = "oldmd5", None
    db.commit()
    hash_calls.clear()
    sid = svc.start_scan(tmp_path)
    assert sorted(hash_calls) == ["a.bin", "b.bin"]
    assert all(r.hash_blake3 for r in db.query(File).all())
    assert db.query(DuplicateGroup).filter_by(scan_id=sid, group_type="exact").count() == 1


def test_hashing_off_reads_nothing(db, tmp_path, hash_calls):
    make(tmp_path, "a.bin", b"x" * 10)
    make(tmp_path, "b.bin", b"x" * 10)
    ScanService(db, compute_hashes=False).start_scan(tmp_path)
    assert hash_calls == [] and rec(db, "a.bin").hash_blake3 is None


@pytest.mark.parametrize("include_hidden", [False, True])
@pytest.mark.parametrize("recursive", [False, True])
def test_size_survey_sees_exactly_the_files_the_real_scan_sees(tmp_path, include_hidden, recursive):
    """If these ever disagree a file could be wrongly skipped and a duplicate missed."""
    make(tmp_path, "a.txt", b"1")
    make(tmp_path, ".hidden", b"22")
    make(tmp_path, "skip.tmp", b"333")                       # excluded extension
    make(tmp_path, "sub/b.txt", b"4444")
    make(tmp_path, "sub/.dot.txt", b"55555")
    make(tmp_path, ".hiddendir/c.txt", b"666666")
    make(tmp_path, "node_modules/d.js", b"7777777")           # excluded folder
    make(tmp_path, "$RECYCLE.BIN/e.txt", b"88888888")
    sc = FileScanner(compute_hashes=False)
    sc.include_hidden = include_hidden
    real = sorted(m.size for m in sc.scan(tmp_path, recursive))
    assert sorted(sc.scan_sizes(tmp_path, recursive)) == real and real


def test_progress_estimate_now_matches_the_real_file_count(db, tmp_path):
    for i in range(7):
        make(tmp_path, f"d{i % 2}/f{i}.txt", b"x" * i)
    svc = ScanService(db)
    total, counts = svc._survey(tmp_path, True)
    assert total == 7 and sum(counts.values()) == 7


def test_usage_step_commits_once_per_batch_and_reports_missing_files(db, tmp_path):
    scan = ScanService(db)
    sid = scan.create_scan(tmp_path)
    paths = []
    for i in range(1200):
        p = tmp_path / f"f{i}.txt"
        p.write_text("x")
        paths.append(p)
        db.add(File(path=str(p), name=p.name, size=1, scan_id=sid))
    db.commit()
    commits = []
    event.listen(db, "after_commit", lambda s: commits.append(1))
    paths.append(tmp_path / "not-indexed.txt")
    (tmp_path / "not-indexed.txt").write_text("x")
    result = UsageService(db).batch_update_usage(paths)
    assert result["updated"] == 1200 and result["failed"] == 1
    assert len(commits) == 3                                  # ceil(1201 / 500), not one per file
    assert db.query(File).filter(File.usage_category.isnot(None)).count() == 1200
