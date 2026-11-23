"""
Path normalization for user-entered scan paths.

Every scan root goes through ``normalize_scan_path`` so that the same folder
always produces the same stored file paths, no matter how the user typed it.
Without this, Windows inputs such as ``D:`` (a *drive-relative* path that
means "the current directory on D:") produced malformed records like
``D:Users\\me\\file.txt``, and differently-cased inputs (``c:\\users`` vs
``C:\\Users``) indexed the same file twice.
"""
from __future__ import annotations

import os
import re
import string
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlparse

IS_WINDOWS = os.name == "nt"

_DRIVE_ONLY = re.compile(r"^([A-Za-z]):$")
_DRIVE_RELATIVE = re.compile(r"^([A-Za-z]):(?![\\/])(.+)$")
_QUOTES = "\"'\u201c\u201d\u2018\u2019"


class ScanPathError(ValueError):
    """Raised when a user-entered path cannot be turned into a scan root."""


def clean_path_text(raw: Optional[str]) -> str:
    """Strip whitespace, wrapping quotes (Explorer's "Copy as path") and file:// URIs."""
    text = (raw or "").strip()
    while len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES:
        text = text[1:-1].strip()
    if text.lower().startswith("file:"):
        parsed = urlparse(text)
        text = unquote(parsed.path or "")
        if IS_WINDOWS and re.match(r"^/[A-Za-z]:", text):
            text = text[1:]
    return text


def normalize_scan_path(raw: Optional[str]) -> Path:
    """
    Turn user input into an absolute, canonical directory path.

    - strips quotes/whitespace and file:// prefixes
    - expands ``~`` and environment variables (``%USERPROFILE%``, ``$HOME``)
    - Windows: ``D:`` -> ``D:\\`` and ``D:folder`` -> ``D:\\folder``
    - resolves ``..``/symlinks and, on Windows, the on-disk letter case

    Raises:
        ScanPathError: input is empty
    """
    text = clean_path_text(raw)
    if not text:
        raise ScanPathError("Enter a folder path to scan.")

    text = os.path.expandvars(os.path.expanduser(text))

    if IS_WINDOWS:
        text = text.replace("/", "\\")
        drive_only = _DRIVE_ONLY.match(text)
        if drive_only:
            text = f"{drive_only.group(1).upper()}:\\"
        else:
            drive_rel = _DRIVE_RELATIVE.match(text)
            if drive_rel:
                text = f"{drive_rel.group(1).upper()}:\\{drive_rel.group(2)}"

    path = Path(text)
    try:
        path = path.resolve(strict=False)
    except (OSError, RuntimeError):
        path = Path(os.path.abspath(text))
    return path


def path_key(path: Path | str) -> str:
    """Case/separator-insensitive comparison key (case-insensitive on Windows)."""
    return os.path.normcase(os.path.normpath(str(path)))


def paths_overlap(a: Path | str, b: Path | str) -> bool:
    """True when a and b are the same folder or one contains the other."""
    ka, kb = path_key(a), path_key(b)
    if ka == kb:
        return True
    sep = os.sep
    ka_dir = ka if ka.endswith(sep) else ka + sep
    kb_dir = kb if kb.endswith(sep) else kb + sep
    return kb.startswith(ka_dir) or ka.startswith(kb_dir)


def describe_path(raw: Optional[str]) -> dict:
    """Validate a path for the UI: normalized form, existence and a friendly message."""
    try:
        path = normalize_scan_path(raw)
    except ScanPathError as exc:
        return {"input": raw or "", "path": "", "exists": False, "is_dir": False,
                "readable": False, "message": str(exc)}

    exists = path.exists()
    is_dir = exists and path.is_dir()
    readable = is_dir and os.access(path, os.R_OK)
    if not exists:
        message = f"Folder not found: {path}"
    elif not is_dir:
        message = f"That is a file, not a folder: {path}"
    elif not readable:
        message = f"No permission to read: {path}"
    else:
        message = "Ready to scan"
    return {
        "input": raw or "",
        "path": str(path),
        "exists": exists,
        "is_dir": is_dir,
        "readable": readable,
        "message": message,
    }


def list_roots() -> List[dict]:
    """Drives (Windows) or / plus common user folders, for quick-pick buttons."""
    roots: List[dict] = []
    if IS_WINDOWS:
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                roots.append({"name": f"{letter}:", "path": drive, "kind": "drive"})
    else:
        roots.append({"name": "/", "path": "/", "kind": "drive"})

    home = Path.home()
    for label in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"):
        candidate = home / label
        if candidate.is_dir():
            roots.append({"name": label, "path": str(candidate), "kind": "folder"})
    roots.insert(len([r for r in roots if r["kind"] == "drive"]),
                 {"name": "Home", "path": str(home), "kind": "folder"})
    return roots


def list_subfolders(raw: Optional[str], include_hidden: bool = False, limit: int = 500) -> dict:
    """List child folders of a directory for the in-app folder picker."""
    if not clean_path_text(raw):
        return {"path": "", "parent": None, "folders": list_roots()}

    path = normalize_scan_path(raw)
    if not path.is_dir():
        raise ScanPathError(f"Folder not found: {path}")

    folders = []
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                if not include_hidden and entry.name.startswith((".", "$")):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        folders.append({"name": entry.name, "path": entry.path, "kind": "folder"})
                except OSError:
                    continue
    except PermissionError as exc:
        raise ScanPathError(f"No permission to open {path}") from exc

    folders.sort(key=lambda f: f["name"].lower())
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "parent": str(parent) if parent else "",
        "folders": folders[:limit],
        "truncated": len(folders) > limit,
    }
