"""
Protected folders - paths the app must never modify.

Two sources:
  * system rules: operating-system and credential folders, built in and not editable
  * user rules:   folders the user adds in Settings (table ``protected_paths``)

A path is protected if it is, or is inside, a protected folder. Both the path as
given and its symlink-resolved form are checked, so a link pointing into a
protected folder cannot be used to get around the rule.

"Modify" means move, rename, sort, delete, or move *into*. Scanning (read-only) is
still allowed. The checks live in the services, not the UI, so they also apply to
the AI assistant, which calls the same services.
"""
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import logging
import os
import sys

from sqlalchemy.orm import Session

from ..db.models import ProtectedPath

logger = logging.getLogger(__name__)


class ProtectedPathError(Exception):
    """Raised when a whole operation targets a protected location"""


def _norm(path) -> str:
    """Absolute, normalized, case-folded on case-insensitive systems (no symlink resolution)"""
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def _real(path) -> str:
    try:
        return os.path.normcase(os.path.realpath(os.path.expanduser(str(path))))
    except OSError:
        return _norm(path)


def _within(child: str, parent: str) -> bool:
    if child == parent:
        return True
    return child.startswith(parent.rstrip('\\/') + os.sep)


def system_rules() -> List[Dict[str, str]]:
    """Built-in protected locations for this operating system"""
    rules: List[Dict[str, str]] = []

    def add(path, reason):
        if path:
            rules.append({'path': str(path), 'reason': reason})

    if sys.platform.startswith('win'):
        drive = os.environ.get('SystemDrive', 'C:') + os.sep
        add(os.environ.get('SystemRoot', drive + 'Windows'), 'Windows system folder')
        add(os.environ.get('ProgramFiles', drive + 'Program Files'), 'Installed programs')
        add(os.environ.get('ProgramFiles(x86)', drive + 'Program Files (x86)'), 'Installed programs')
        add(os.environ.get('ProgramData', drive + 'ProgramData'), 'Shared program data')
        add(drive + 'System Volume Information', 'Windows restore data')
        add(drive + '$Recycle.Bin', 'Recycle Bin')
        add(os.path.join(Path.home(), 'AppData'), 'Application data (moving files here breaks programs)')
    else:
        for p in ('/bin', '/boot', '/dev', '/etc', '/lib', '/lib32', '/lib64', '/proc', '/sbin', '/sys',
                  '/usr', '/opt', '/var/lib', '/var/log', '/var/db', '/var/spool',
                  '/System', '/Library', '/Applications', '/private/etc', '/private/var/db'):
            add(p, 'Operating system or installed software')

    for name in ('.ssh', '.gnupg', '.aws', '.azure', '.kube'):
        add(os.path.join(Path.home(), name), 'Credentials and keys')
    return rules


class ProtectionService:
    def __init__(self, db: Session):
        self.db = db
        self._rules: Optional[List[Dict[str, str]]] = None

    # ---- rules -----------------------------------------------------------
    def _all_rules(self) -> List[Dict[str, str]]:
        """System rules plus user rules, each with normalized forms precomputed (cached per instance)"""
        if self._rules is None:
            rules = []
            for r in system_rules():
                rules.append({**r, 'kind': 'system', 'n': _norm(r['path']), 'r': _real(r['path'])})
            for row in self.db.query(ProtectedPath).all():
                rules.append({'path': row.path, 'reason': row.note or 'Protected by you', 'kind': 'user',
                              'n': _norm(row.path), 'r': _real(row.path)})
            self._rules = rules
        return self._rules

    def blocked_reason(self, path) -> Optional[str]:
        """Why this path may not be modified, or None if it is allowed"""
        cn, cr = _norm(path), _real(path)
        for rule in self._all_rules():
            if _within(cn, rule['n']) or _within(cr, rule['r']) or _within(cn, rule['r']) or _within(cr, rule['n']):
                return f"Protected: {rule['reason']} ({rule['path']})"
        return None

    def blocked(self, paths: Iterable) -> List[Dict[str, str]]:
        out = []
        for p in paths:
            reason = self.blocked_reason(p)
            if reason:
                out.append({'path': str(p), 'reason': reason})
        return out

    def require_allowed(self, path, what: str = 'This location') -> None:
        reason = self.blocked_reason(path)
        if reason:
            raise ProtectedPathError(f"{what} is protected and cannot be changed. {reason}")

    # ---- management ------------------------------------------------------
    def list(self) -> Dict:
        user = self.db.query(ProtectedPath).order_by(ProtectedPath.created_at).all()
        return {
            'system': system_rules(),
            'user': [{'id': r.id, 'path': r.path, 'note': r.note, 'created_at': r.created_at.isoformat()} for r in user],
        }

    def add(self, path: str, note: Optional[str] = None) -> Dict:
        from .scan_service import normalize_scan_path  # bare "D:" -> "D:\"

        text = str(path or '').strip()
        if not text:
            raise ValueError('Enter a folder path')
        p = normalize_scan_path(text)
        if not os.path.isabs(os.path.expanduser(str(p))):
            raise ValueError('Use a full path, for example C:\\Users\\You\\Documents')
        stored = str(os.path.abspath(os.path.expanduser(str(p))))
        existing = next((r for r in self.db.query(ProtectedPath).all() if _norm(r.path) == _norm(stored)), None)
        if existing:
            return {'id': existing.id, 'path': existing.path, 'note': existing.note, 'already': True}
        row = ProtectedPath(path=stored, note=(note or '').strip()[:256] or None)
        self.db.add(row)
        self.db.commit()
        return {'id': row.id, 'path': row.path, 'note': row.note, 'already': False}

    def remove(self, protected_id: str) -> bool:
        row = self.db.query(ProtectedPath).filter_by(id=protected_id).first()
        if row is None:
            return False
        self.db.delete(row)
        self.db.commit()
        return True
