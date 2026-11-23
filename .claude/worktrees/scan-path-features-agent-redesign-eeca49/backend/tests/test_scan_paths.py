"""
Regression tests for scan path handling.

Run from backend/:  python -m unittest tests.test_scan_paths -v
"""
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from app.db import connection
from app.db.models import File, ScanSession
from app.utils.path_utils import (
    IS_WINDOWS,
    clean_path_text,
    describe_path,
    normalize_scan_path,
    paths_overlap,
    ScanPathError,
)


class NormalizeTests(unittest.TestCase):
    def test_strips_quotes_and_whitespace(self):
        self.assertEqual(clean_path_text('  "C:\\Data\\Photos"  '), "C:\\Data\\Photos")
        self.assertEqual(clean_path_text("'/tmp/x'"), "/tmp/x")

    def test_empty_raises(self):
        with self.assertRaises(ScanPathError):
            normalize_scan_path("   ")

    def test_file_uri(self):
        tmp = tempfile.mkdtemp()
        try:
            uri = Path(tmp).as_uri()
            self.assertEqual(normalize_scan_path(uri), Path(tmp).resolve())
        finally:
            shutil.rmtree(tmp)

    def test_env_and_home(self):
        self.assertEqual(normalize_scan_path("~"), Path.home().resolve())

    @unittest.skipUnless(IS_WINDOWS, "drive letters are Windows-only")
    def test_bare_drive_means_drive_root(self):
        # "C:" alone is drive-relative in Windows (current dir on C:); users mean C:\
        self.assertEqual(str(normalize_scan_path("c:")), "C:\\")
        self.assertEqual(str(normalize_scan_path("C:/")), "C:\\")

    @unittest.skipUnless(IS_WINDOWS, "drive letters are Windows-only")
    def test_drive_relative_folder(self):
        self.assertTrue(str(normalize_scan_path("C:Windows")).upper().startswith("C:\\WINDOWS"))

    @unittest.skipUnless(IS_WINDOWS, "case-insensitive paths are Windows-only")
    def test_real_letter_case(self):
        tmp = Path(tempfile.mkdtemp(prefix="CaseTest"))
        try:
            self.assertEqual(normalize_scan_path(str(tmp).lower()), tmp.resolve())
        finally:
            shutil.rmtree(tmp)

    def test_overlap(self):
        base = Path(tempfile.gettempdir()).resolve()
        self.assertTrue(paths_overlap(base, base / "a"))
        self.assertTrue(paths_overlap(base / "a", base))
        self.assertFalse(paths_overlap(base / "a", base / "ab"))

    def test_describe_missing(self):
        info = describe_path(os.path.join(tempfile.gettempdir(), "definitely-missing-ssm"))
        self.assertFalse(info["exists"])
        self.assertIn("not found", info["message"])


class ScanServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="SsmScan")).resolve()
        self.db_file = self.tmp / "test.db"
        self.root = self.tmp / "Root"
        (self.root / "Sub").mkdir(parents=True)
        (self.root / "a.txt").write_text("same")
        (self.root / "Sub" / "b.txt").write_text("same")
        (self.root / "Sub" / "c.txt").write_text("different")
        connection.init_db(f"sqlite:///{self.db_file.as_posix()}")
        connection.create_all_tables()

    def tearDown(self):
        connection.get_engine().dispose()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _scan(self, raw_path):
        from app.services.scan_service import ScanService
        db = connection.get_session()
        try:
            return ScanService(db).start_scan(raw_path)
        finally:
            db.close()

    def test_rescan_with_different_spelling_does_not_duplicate_rows(self):
        first = self._scan(str(self.root))
        spelled = f'  "{str(self.root).lower() if IS_WINDOWS else self.root}"  '
        second = self._scan(spelled)

        db = connection.get_session()
        try:
            paths = [p for (p,) in db.query(File.path).all()]
            self.assertEqual(len(paths), 3, paths)
            self.assertEqual(len({p.lower() for p in paths}), 3)
            self.assertTrue(all(p.startswith(str(self.root)) for p in paths), paths)
            s1 = db.query(ScanSession).filter_by(id=first).one()
            s2 = db.query(ScanSession).filter_by(id=second).one()
            self.assertEqual((s1.status, s2.status), ("completed", "completed"))
            self.assertEqual(s2.start_path, str(self.root))
            self.assertEqual(db.query(File).filter_by(scan_id=second).count(), 3)
        finally:
            db.close()

        from app.services.scan_service import get_live_progress
        self.assertEqual(get_live_progress(second)["hashes_reused"], 3)
        self.assertEqual(get_live_progress(second)["potential_savings"], 4)

    def test_overlapping_scan_is_refused(self):
        from app.services import scan_service as svc
        gate = threading.Event()
        release = threading.Event()
        original = svc.ScanService.run_scan

        def slow_run(self, *args, **kwargs):
            gate.set()
            release.wait(5)
            return original(self, *args, **kwargs)

        svc.ScanService.run_scan = slow_run
        try:
            db = connection.get_session()
            scan_id = svc.ScanService(db).start_scan_background(str(self.root))
            gate.wait(5)
            with self.assertRaises(svc.ScanConflictError) as same:
                svc.ScanService(db).start_scan_background(str(self.root))
            self.assertTrue(same.exception.same_path)
            self.assertEqual(same.exception.scan_id, scan_id)
            with self.assertRaises(svc.ScanConflictError) as child:
                svc.ScanService(db).start_scan_background(str(self.root / "Sub"))
            self.assertFalse(child.exception.same_path)
            db.close()
        finally:
            release.set()
            svc.ScanService.run_scan = original
            for _ in range(100):
                if not svc.active_scans():
                    break
                threading.Event().wait(0.05)

    def test_missing_folder_raises(self):
        from app.services.scan_service import ScanService
        db = connection.get_session()
        try:
            with self.assertRaises(FileNotFoundError):
                ScanService(db).start_scan_background(str(self.root / "nope"))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
