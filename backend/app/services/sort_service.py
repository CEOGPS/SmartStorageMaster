"""
Auto-sort service - plan and apply sorting of indexed files into subfolders.

Modes: ``type`` (image/document/video/...), ``extension`` (jpg, pdf, ...), ``date``
(modified year or year-month). Every sort is previewed first; ``apply`` recomputes
the plan on the server (never trusts a client-supplied plan) and records the whole
batch in the undo journal as a single operation.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging
import re
import shutil

from sqlalchemy.orm import Session

from ..db.models import File
from .journal_service import JournalService, retarget_file_record
from .organizer_service import _categorize
from .scan_service import normalize_scan_path

logger = logging.getLogger(__name__)

MODES = ('type', 'extension', 'date')
DATE_GRANULARITIES = ('year', 'month')
PREVIEW_LIMIT = 200
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_folder(name: str) -> str:
    cleaned = _UNSAFE.sub('_', name).strip(' .')
    return cleaned or 'other'


class SortService:
    def __init__(self, db: Session):
        self.db = db

    def _folder_for(self, rec: File, mode: str, granularity: str) -> str:
        if mode == 'type':
            return _categorize(rec.mime_type, rec.name).capitalize()
        if mode == 'extension':
            ext = Path(rec.name).suffix.lower().lstrip('.')
            return _safe_folder(ext) if ext else 'no-extension'
        when = rec.modified_at or datetime.utcnow()
        return f"{when:%Y}" if granularity == 'year' else f"{when:%Y}-{when:%m}"

    def _candidates(self, source: Path, recursive: bool) -> List[File]:
        prefix = str(source).rstrip('\\/')
        escaped = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        rows = self.db.query(File).filter(File.path.like(escaped + '%', escape='\\')).all()
        out = []
        for rec in rows:
            p = Path(rec.path)
            if recursive:
                if source in p.parents:
                    out.append(rec)
            elif p.parent == source:
                out.append(rec)
        return sorted(out, key=lambda r: r.path)

    def plan(self, source: str, mode: str, granularity: str = 'year',
             recursive: bool = False, destination: Optional[str] = None) -> Dict:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if granularity not in DATE_GRANULARITIES:
            raise ValueError(f"granularity must be one of {DATE_GRANULARITIES}")
        src_root = normalize_scan_path(source)
        if not src_root.is_dir():
            raise ValueError(f"Source is not a directory: {src_root}")
        dest_root = normalize_scan_path(destination) if destination else src_root

        taken = set()
        moves: List[Dict] = []
        skipped = 0
        for rec in self._candidates(src_root, recursive):
            src = Path(rec.path)
            if not src.exists():
                skipped += 1
                continue
            folder = self._folder_for(rec, mode, granularity)
            dst = dest_root / folder / src.name
            if dst == src:
                continue  # already where it belongs
            counter = 1
            while dst.exists() or str(dst) in taken:
                dst = dest_root / folder / f"{src.stem} ({counter}){src.suffix}"
                counter += 1
            taken.add(str(dst))
            moves.append({'file_id': rec.id, 'src': str(src), 'dst': str(dst), 'folder': folder})

        folders: Dict[str, int] = {}
        for m in moves:
            folders[m['folder']] = folders.get(m['folder'], 0) + 1
        return {
            'mode': mode, 'total': len(moves), 'missing_on_disk': skipped,
            'folders': folders, 'moves': moves,
            'preview': moves[:PREVIEW_LIMIT], 'truncated': len(moves) > PREVIEW_LIMIT,
        }

    def apply(self, source: str, mode: str, granularity: str = 'year',
              recursive: bool = False, destination: Optional[str] = None) -> Dict:
        plan = self.plan(source, mode, granularity, recursive, destination)
        journal = JournalService(self.db)
        op = journal.begin('sort', f"Sort by {mode}: {plan['total']} file(s) in {source}")
        self.db.commit()  # the operation exists before any file moves
        moved, failed = 0, []
        for m in plan['moves']:
            src, dst = Path(m['src']), Path(m['dst'])
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():  # appeared since planning; never overwrite
                    raise FileExistsError(str(dst))
                shutil.move(str(src), str(dst))
            except Exception as e:
                failed.append({'path': m['src'], 'reason': str(e)})
                continue
            try:
                # Save each move on its own so an undo record always exists for
                # every file that actually moved.
                journal.record(op, src, dst, m['file_id'])
                retarget_file_record(self.db, m['file_id'], dst)
                self.db.commit()
                moved += 1
            except Exception as e:
                self.db.rollback()
                try:
                    shutil.move(str(dst), str(src))  # keep disk and index consistent
                except Exception:
                    logger.error(f"Could not roll back move of {src}", exc_info=True)
                failed.append({'path': m['src'], 'reason': f'index update failed: {e}'})
        journal.discard_if_empty(op)
        self.db.commit()
        return {'moved': moved, 'failed': failed, 'operation_id': op.id if moved else None,
                'folders': plan['folders']}
