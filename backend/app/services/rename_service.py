"""
Bulk rename service - plan and apply batch renames with a live preview.

A rename is described by a template plus optional find/replace:

  find / replace     applied to the original name (without extension) first.
                     Literal by default; ``use_regex`` enables Python regex with
                     \\1 or \\g<name> back-references.
  template           builds the new name (without extension). Tokens:
                       {name}            name after find/replace
                       {n} {n:3}         sequence number (zero-padded to 3)
                       {date} {date:%Y-%m-%d}       modified date/time
                       {created:%Y%m%d_%H%M%S}      created date/time
                       {parent}          containing folder name
                       {size_kb}         size in KB
  case               none | lower | upper | title (applied to the result)
  ext_case           keep | lower | upper (extension is always kept)

Safety: never overwrites. Targets that are invalid on Windows, collide with a
file outside the batch, or duplicate another target are reported and skipped.
Renames run in two phases (original -> temporary -> final) so swaps and
renumbering (img1->img2, img2->img3) work, and every hop is journaled so the
whole batch can be undone.
"""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging
import re
import uuid

from sqlalchemy.orm import Session

from ..db.models import File
from .journal_service import JournalService, retarget_file_record
from .scan_service import normalize_scan_path

logger = logging.getLogger(__name__)

PREVIEW_LIMIT = 500
ORDERS = ('name', 'modified', 'size')
CASES = ('none', 'lower', 'upper', 'title')
EXT_CASES = ('keep', 'lower', 'upper')
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
_TOKEN = re.compile(r'\{(\w+)(?::([^{}]*))?\}')
_KNOWN = {'name', 'n', 'date', 'created', 'parent', 'size_kb'}


def validate_name(name: str) -> Optional[str]:
    """Return a reason the name is unusable on Windows/macOS/Linux, or None"""
    if not name or not name.strip():
        return 'name is empty'
    if _INVALID_CHARS.search(name):
        return 'contains a character not allowed in file names (< > : " / \\ | ? *)'
    if name[-1] in ' .':
        return 'ends with a space or dot'
    if name.split('.')[0].upper() in _RESERVED:
        return 'is a reserved Windows name'
    if len(name.encode('utf-8')) > 255:
        return 'is longer than 255 bytes'
    return None


class RenameError(ValueError):
    pass


class RenameService:
    def __init__(self, db: Session):
        self.db = db

    # ---- selection -------------------------------------------------------
    def _select(self, file_ids: Optional[List[str]], folder: Optional[str],
                recursive: bool, match: Optional[str]) -> List[File]:
        if file_ids:
            rows = self.db.query(File).filter(File.id.in_(file_ids)).all()
        elif folder:
            root = normalize_scan_path(folder)
            if not root.is_dir():
                raise RenameError(f'Folder does not exist: {root}')
            prefix = str(root).rstrip('\\/')
            esc = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            rows = [r for r in self.db.query(File).filter(File.path.like(esc + '%', escape='\\')).all()
                    if (root in Path(r.path).parents if recursive else Path(r.path).parent == root)]
        else:
            raise RenameError('Choose a folder or select files to rename')
        if match:
            try:
                rx = re.compile(match, re.IGNORECASE)
            except re.error as e:
                raise RenameError(f'Filter is not a valid regular expression: {e}')
            rows = [r for r in rows if rx.search(r.name)]
        return rows

    # ---- naming ----------------------------------------------------------
    @staticmethod
    def _render(template: str, values: Dict, seq: int) -> str:
        def sub(m):
            key, fmt = m.group(1), m.group(2)
            if key not in _KNOWN:
                raise RenameError(f'Unknown token {{{key}}}. Use one of: ' + ', '.join(f'{{{k}}}' for k in sorted(_KNOWN)))
            if key == 'n':
                width = int(fmt) if fmt and fmt.isdigit() else 1
                return str(seq).zfill(width)
            if key in ('date', 'created'):
                return values[key].strftime(fmt or '%Y-%m-%d')
            return str(values[key])
        return _TOKEN.sub(sub, template)

    def plan(self, *, template: str = '{name}', find: str = '', replace: str = '',
             use_regex: bool = False, case_sensitive: bool = False, case: str = 'none',
             ext_case: str = 'keep', start: int = 1, step: int = 1, order: str = 'name',
             file_ids: Optional[List[str]] = None, folder: Optional[str] = None,
             recursive: bool = False, match: Optional[str] = None) -> Dict:
        if case not in CASES or ext_case not in EXT_CASES or order not in ORDERS:
            raise RenameError('Invalid case, ext_case or order option')
        if not template.strip():
            raise RenameError('Template is empty')
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            finder = re.compile(find if use_regex else re.escape(find), flags) if find else None
        except re.error as e:
            raise RenameError(f'Find is not a valid regular expression: {e}')

        rows = self._select(file_ids, folder, recursive, match)
        keys = {'name': lambda r: r.name.lower(),
                'modified': lambda r: (r.modified_at or datetime.min, r.name.lower()),
                'size': lambda r: (r.size or 0, r.name.lower())}
        rows.sort(key=keys[order])

        items, targets = [], {}
        batch_paths = {str(Path(r.path)).lower() for r in rows}
        seq = start
        for r in rows:
            src = Path(r.path)
            stem, ext = src.stem, src.suffix
            name = stem
            if finder:
                try:
                    name = finder.sub(replace, stem) if use_regex else finder.sub(lambda _m: replace, stem)
                except (re.error, IndexError) as e:
                    raise RenameError(f'Replace is not valid for this pattern: {e}')
            values = {'name': name, 'date': r.modified_at or datetime.utcnow(),
                      'created': r.created_at or r.modified_at or datetime.utcnow(),
                      'parent': src.parent.name, 'size_kb': round((r.size or 0) / 1024)}
            new_stem = self._render(template, values, seq)
            seq += step
            new_stem = {'lower': str.lower, 'upper': str.upper, 'title': str.title}.get(case, lambda s: s)(new_stem)
            new_ext = {'lower': ext.lower(), 'upper': ext.upper()}.get(ext_case, ext)
            new_name = new_stem + new_ext
            dst = src.with_name(new_name)

            item = {'file_id': r.id, 'path': str(src), 'old_name': src.name, 'new_name': new_name,
                    'status': 'ok', 'reason': None}
            reason = validate_name(new_name)
            key = str(dst).lower()
            if reason:
                item.update(status='error', reason=f'New name {reason}')
            elif new_name == src.name:
                item.update(status='unchanged')
            elif key in targets:
                item.update(status='conflict', reason=f'Same new name as {targets[key]}')
            elif dst.exists() and key not in batch_paths and str(dst).lower() != str(src).lower():
                item.update(status='conflict', reason='A file with this name already exists')
            if item['status'] in ('ok', 'unchanged'):
                targets[key] = src.name
            if not src.exists():
                item.update(status='error', reason='File no longer exists on disk (re-scan)')
            items.append(item)

        # A target may equal another batch file's *current* name only if that
        # file is itself being renamed away; otherwise it would be overwritten.
        moving = {i['path'].lower() for i in items if i['status'] == 'ok'}
        for i in items:
            if i['status'] != 'ok':
                continue
            dst_key = str(Path(i['path']).with_name(i['new_name'])).lower()
            if dst_key in batch_paths and dst_key not in moving and dst_key != i['path'].lower():
                i.update(status='conflict', reason='Another file in this batch keeps that name')

        counts = {s: sum(1 for i in items if i['status'] == s) for s in ('ok', 'unchanged', 'conflict', 'error')}
        return {'total': len(items), 'counts': counts, 'items': items,
                'preview': items[:PREVIEW_LIMIT], 'truncated': len(items) > PREVIEW_LIMIT}

    def apply(self, **opts) -> Dict:
        plan = self.plan(**opts)
        todo = [i for i in plan['items'] if i['status'] == 'ok']
        journal = JournalService(self.db)
        op = journal.begin('rename', f"Rename {len(todo)} file(s)")
        self.db.commit()
        failed: List[Dict] = []
        tag = uuid.uuid4().hex[:8]

        # Phase 1: original -> temporary unique name (frees every original name)
        staged = []
        for i in todo:
            src = Path(i['path'])
            tmp = src.with_name(f'.ssm-rename-{tag}-{len(staged)}{src.suffix}')
            try:
                if tmp.exists():
                    raise FileExistsError(str(tmp))
                src.rename(tmp)
                journal.record(op, src, tmp, i['file_id'])
                retarget_file_record(self.db, i['file_id'], tmp)
                self.db.commit()
                staged.append((i, src, tmp))
            except Exception as e:
                self.db.rollback()
                if tmp.exists() and not src.exists():
                    tmp.rename(src)
                failed.append({'path': str(src), 'reason': str(e)})

        # Phase 2: temporary -> final name
        renamed = 0
        for i, src, tmp in staged:
            dst = src.with_name(i['new_name'])
            try:
                if dst.exists() and str(dst).lower() != str(src).lower():
                    raise FileExistsError(f'{dst.name} appeared since the preview')
                tmp.rename(dst)
                journal.record(op, tmp, dst, i['file_id'])
                retarget_file_record(self.db, i['file_id'], dst)
                self.db.commit()
                renamed += 1
            except Exception as e:
                self.db.rollback()
                # Put the file back under its original name rather than leave a temp name
                try:
                    if tmp.exists() and not src.exists():
                        tmp.rename(src)
                        journal.record(op, tmp, src, i['file_id'])
                        retarget_file_record(self.db, i['file_id'], src)
                        self.db.commit()
                except Exception:
                    self.db.rollback()
                    logger.error(f'Could not restore {src} from {tmp}', exc_info=True)
                failed.append({'path': str(src), 'reason': str(e)})

        journal.discard_if_empty(op)
        self.db.commit()
        return {'renamed': renamed, 'failed': failed, 'skipped': plan['counts']['conflict'] + plan['counts']['error'],
                'operation_id': op.id if renamed else None}
