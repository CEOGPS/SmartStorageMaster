"""
Undo journal - records file moves/renames so a whole batch can be reversed.

Safety rules: undo never overwrites an existing file, never touches a file that
is no longer at the recorded destination, and reports every skipped item.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging
import shutil

from sqlalchemy.orm import Session

from ..db.models import File, Operation, OperationItem
from .protection_service import ProtectionService

logger = logging.getLogger(__name__)


def retarget_file_record(db: Session, file_id: Optional[str], new_path: Path) -> None:
    """
    Point an indexed file at its new path.

    Callers guarantee nothing existed on disk at ``new_path`` (the move/undo only
    proceeds into a free spot), so any other index row at that path is stale
    (e.g. left by an earlier scan) and is dropped to keep files.path unique.
    """
    if not file_id:
        return
    rec = db.query(File).filter_by(id=file_id).first()
    if rec is None:
        return
    for stale in db.query(File).filter(File.path == str(new_path), File.id != file_id).all():
        db.delete(stale)
    db.flush()
    rec.path, rec.name = str(new_path), new_path.name


class JournalService:
    def __init__(self, db: Session):
        self.db = db

    def begin(self, kind: str, summary: str = "") -> Operation:
        op = Operation(kind=kind, summary=summary[:512])
        self.db.add(op)
        self.db.flush()
        return op

    def record(self, op: Operation, src: Path, dst: Path, file_id: Optional[str] = None) -> None:
        op.items.append(OperationItem(
            seq=len(op.items), file_id=file_id, src_path=str(src), dst_path=str(dst),
        ))

    def discard_if_empty(self, op: Operation) -> None:
        if not op.items:
            self.db.delete(op)

    def list_operations(self, limit: int = 50) -> List[Dict]:
        ops = (self.db.query(Operation).order_by(Operation.created_at.desc()).limit(limit).all())
        return [{
            'id': o.id, 'kind': o.kind, 'summary': o.summary,
            'created_at': o.created_at.isoformat(), 'undone': o.undone_at is not None,
            'item_count': len(o.items),
        } for o in ops]

    def undo(self, operation_id: str) -> Dict:
        op = self.db.query(Operation).filter_by(id=operation_id).first()
        if op is None:
            raise LookupError("Operation not found")
        if op.undone_at is not None:
            raise ValueError("Operation was already undone")

        restored, skipped = 0, []
        protection = ProtectionService(self.db)
        for item in reversed(op.items):
            if item.undone:
                continue
            src, dst = Path(item.src_path), Path(item.dst_path)
            reason = protection.blocked_reason(src) or protection.blocked_reason(dst)
            if reason:
                skipped.append({'path': item.dst_path, 'reason': reason})
                continue
            if not dst.exists():
                skipped.append({'path': item.dst_path, 'reason': 'file no longer at destination'})
                continue
            if src.exists():
                skipped.append({'path': item.src_path, 'reason': 'original location is occupied'})
                continue
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
            except Exception as e:  # report, keep going
                skipped.append({'path': item.dst_path, 'reason': str(e)})
                continue
            item.undone = True
            restored += 1
            retarget_file_record(self.db, item.file_id, src)

        if not skipped:
            op.undone_at = datetime.utcnow()
        self.db.commit()
        return {'restored': restored, 'skipped': skipped, 'fully_undone': not skipped}
