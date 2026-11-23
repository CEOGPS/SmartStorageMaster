"""
AI agent chat endpoint

Exposes a natural-language chat interface over the existing REST services
(scan, duplicates, usage, cleanup) using tool-calling against a LOCAL Ollama
model (no cloud API, no API key). This is purely additive - it reuses the
same service classes the other routers use, so every action it takes is
identical to what the corresponding page button would do.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pathlib import Path
from typing import List, Optional
import json
import logging
import os
import time

import requests

from ...db import get_db
from ...services.scan_service import ScanService, ScanConflictError, get_live_progress
from ...utils.path_utils import ScanPathError
from ...services.duplicate_service import DuplicateService
from ...services.usage_service import UsageService
from ...services.cleanup_service import CleanupService
from ...api.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Local Ollama configuration - configurable via env vars so the user can
# swap models/hosts later without a code change. Defaults match the user's
# confirmed local setup (llama3.2:latest, supports tool-calling).
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:latest")

MAX_TOOL_ROUNDS = 6
OLLAMA_TIMEOUT_SECONDS = 60

CONFIRM_KEYWORDS = (
    "yes", "yep", "yeah", "confirm", "confirmed", "go ahead", "go for it",
    "do it", "delete them", "delete it", "remove them", "remove it",
    "sounds good", "proceed", "sure", "ok delete", "okay delete",
    "approve", "approved",
)

SYSTEM_PROMPT = """You are the in-app assistant for Storage Manager Pro, a desktop storage \
management tool. You help the user find and clean up files on their computer by calling \
tools that wrap the app's own scan/duplicate/usage/cleanup features - the exact same \
operations the app's buttons perform.

Guidelines:
- Prefer read-only tools (start_scan, get_storage_stats, detect_duplicates, \
get_duplicate_groups, get_usage_recommendations, get_backups) to gather information and \
propose a plan.
- NEVER call backup_files or delete_files unless the user has explicitly confirmed in \
their OWN message that they want files deleted (e.g. "yes delete them", "go ahead", \
"confirmed, remove them"). If this is the first time the user is asking about cleaning up \
duplicates/files, you must NOT delete or back up anything yet - instead, investigate with \
the read-only tools and reply with a clear, specific plan (which files/groups, how much \
space would be freed) and ask the user to confirm before you touch anything.
- Only once the user has confirmed in a later message should you proceed: call \
backup_files first, then delete_files, mirroring the app's own Cleanup page flow (always \
back up before deleting - never delete without a preceding backup in the same confirmed \
action).
- Scans run in the background. When you start one, tell the user it is running and that \
they can watch progress on the Scan page; do not block pretending it already finished.
- Be concise and concrete: name file counts, sizes, and paths when you have them.
"""


def _get_tools(allow_destructive: bool) -> List[dict]:
    """Ollama uses the same OpenAI-style function-tool JSON schema as other
    tool-calling APIs: {"type": "function", "function": {name, description, parameters}}.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "start_scan",
                "description": (
                    "Start scanning a directory for files (kicks off a background scan, "
                    "same as the Scan page's Start Scan button). Returns a scan_id."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute directory path to scan"},
                        "recursive": {"type": "boolean", "default": True},
                        "include_hidden": {"type": "boolean", "default": False},
                        "compute_hash": {"type": "boolean", "default": True},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_storage_stats",
                "description": "Get overall storage statistics from the most recent completed scan.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "detect_duplicates",
                "description": (
                    "Run duplicate detection (exact hash and/or near-duplicate image) over a "
                    "completed scan's files."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scan_id": {"type": "string"},
                        "detect_exact": {"type": "boolean", "default": True},
                        "detect_images": {"type": "boolean", "default": True},
                        "image_similarity": {"type": "number", "default": 0.85},
                    },
                    "required": ["scan_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_duplicate_groups",
                "description": "Get the duplicate file groups detected for a scan, with file ids/paths/sizes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scan_id": {"type": "string"},
                        "group_type": {
                            "type": "string",
                            "description": "Optional filter: exact, phash, embedding",
                        },
                    },
                    "required": ["scan_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_usage_recommendations",
                "description": (
                    "Get prioritized cleanup recommendations - files that are rarely/never used, "
                    "sorted by cleanup priority."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 100},
                        "min_priority": {"type": "number", "default": 0.7},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_backups",
                "description": "List current file backups (files that have already been backed up before deletion).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    if allow_destructive:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "backup_files",
                    "description": (
                        "Back up the given file ids before deleting them. ALWAYS call this before "
                        "delete_files, and only after the user has explicitly confirmed deletion."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["file_ids"],
                    },
                },
            }
        )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "delete_files",
                    "description": (
                        "Permanently delete the given file ids from disk. Only call this after "
                        "backup_files has been called for the same ids in this conversation, and "
                        "only after the user explicitly confirmed deletion."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["file_ids"],
                    },
                },
            }
        )

    return tools


def _execute_tool(name: str, tool_input: dict, db: Session) -> dict:
    """Execute a tool by calling straight into the existing service classes."""
    if name == "start_scan":
        compute_hash = tool_input.get("compute_hash", True)
        service = ScanService(db, compute_hashes=compute_hash)
        try:
            scan_id = service.start_scan_background(
                tool_input.get("path", ""),
                recursive=tool_input.get("recursive", True),
                include_hidden=tool_input.get("include_hidden", False),
            )
        except ScanConflictError as e:
            if not e.same_path:
                return {"error": str(e), "running_scan_id": e.scan_id}
            return {"scan_id": e.scan_id, "status": "running",
                    "message": f"That folder is already being scanned ({e.path})."}
        except (ScanPathError, FileNotFoundError, NotADirectoryError) as e:
            return {"error": str(e)}

        # Briefly poll for progress so a fast scan can report real numbers,
        # but never block the agent loop waiting for a long-running scan.
        status = "running"
        for _ in range(4):
            time.sleep(0.5)
            progress = get_live_progress(scan_id)
            if progress:
                status = progress.get("status", "running")
            if status in ("completed", "failed"):
                break

        if status == "completed":
            return {
                "scan_id": scan_id,
                "status": "completed",
                "message": "Scan finished quickly - use get_storage_stats or detect_duplicates next.",
            }
        return {
            "scan_id": scan_id,
            "status": status,
            "message": (
                "Scan started in the background. It may take a while for large folders - "
                "the user can watch live progress on the Scan page."
            ),
        }

    if name == "get_storage_stats":
        return ScanService(db).get_storage_stats()

    if name == "detect_duplicates":
        service = DuplicateService(db)
        scan_id = tool_input["scan_id"]
        exact_groups: List[str] = []
        image_groups: List[str] = []
        if tool_input.get("detect_exact", True):
            exact_groups = service.detect_exact_duplicates(scan_id)
        if tool_input.get("detect_images", True):
            image_groups = service.detect_image_duplicates(
                scan_id, tool_input.get("image_similarity", 0.85)
            )
        return {
            "exact_groups": len(exact_groups),
            "image_groups": len(image_groups),
            "total_groups": len(exact_groups) + len(image_groups),
            "group_ids": exact_groups + image_groups,
        }

    if name == "get_duplicate_groups":
        groups = DuplicateService(db).get_duplicate_groups(
            tool_input["scan_id"], tool_input.get("group_type")
        )
        return {"groups": groups, "count": len(groups)}

    if name == "get_usage_recommendations":
        recs = UsageService(db).get_cleanup_recommendations(
            limit=tool_input.get("limit", 100),
            min_priority=tool_input.get("min_priority", 0.7),
        )
        return {
            "count": len(recs),
            "total_potential_cleanup_mb": round(sum(r["size_mb"] for r in recs), 2),
            "recommendations": recs,
        }

    if name == "get_backups":
        backups = CleanupService(db).get_backups()
        return {"backups": backups, "count": len(backups)}

    if name == "backup_files":
        return CleanupService(db).backup_files(tool_input["file_ids"])

    if name == "delete_files":
        return CleanupService(db).delete_files(tool_input["file_ids"])

    return {"error": f"Unknown tool: {name}"}


def _summarize_result(name: str, result: dict) -> str:
    if "error" in result:
        return f"{name}: error - {result['error']}"
    if name == "start_scan":
        return f"start_scan: scan_id={result.get('scan_id')} status={result.get('status')}"
    if name == "get_storage_stats":
        return f"get_storage_stats: {result.get('total_files', 0)} files, {result.get('total_size_formatted', '0 B')}"
    if name == "detect_duplicates":
        return f"detect_duplicates: {result.get('total_groups', 0)} duplicate group(s) found"
    if name == "get_duplicate_groups":
        return f"get_duplicate_groups: {result.get('count', 0)} group(s)"
    if name == "get_usage_recommendations":
        return f"get_usage_recommendations: {result.get('count', 0)} file(s), ~{result.get('total_potential_cleanup_mb', 0)} MB"
    if name == "get_backups":
        return f"get_backups: {result.get('count', 0)} backup(s) on record"
    if name == "backup_files":
        return f"backup_files: backed up {result.get('backed_up', 0)}/{result.get('total', 0)}"
    if name == "delete_files":
        return f"delete_files: deleted {result.get('deleted', 0)}/{result.get('total', 0)}"
    return f"{name}: done"


def _looks_like_confirmation(message: str) -> bool:
    lowered = message.lower()
    return any(kw in lowered for kw in CONFIRM_KEYWORDS)


def _call_ollama(messages: List[dict], tools: List[dict]) -> dict:
    """POST to the local Ollama /api/chat endpoint. Raises requests exceptions
    on connection/HTTP failure - caller is responsible for turning those into
    the JSON error shape."""
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "tools": tools,
            "stream": False,
        },
        timeout=OLLAMA_TIMEOUT_SECONDS,
    )
    resp.raise_for_status()
    return resp.json()


@router.get("/status", response_model=dict)
def agent_status():
    """Whether the local Ollama model is reachable, for the dock's status light."""
    online = False
    model_installed = False
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        online = resp.ok
        if online:
            names = {m.get("name") for m in resp.json().get("models", [])}
            model_installed = OLLAMA_MODEL in names
    except (requests.RequestException, ValueError):
        online = False
    return {
        "success": True,
        "data": {"online": online, "model": OLLAMA_MODEL, "model_installed": model_installed},
    }


@router.post("/chat", response_model=dict)
def agent_chat(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Natural-language chat endpoint backed by tool-calling against a local
    Ollama model - no cloud API, no API key required.
    """
    try:
        history = request.history or []

        # Defense in depth: only expose the destructive tools once the
        # conversation already has a prior assistant turn (i.e. the model
        # already proposed something) AND the latest user message reads as
        # a confirmation. Otherwise keep the model to read-only tools.
        has_prior_assistant_turn = any(h.role == "assistant" for h in history)
        allow_destructive = has_prior_assistant_turn and _looks_like_confirmation(request.message)

        messages: List[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": h.role, "content": h.content} for h in history)
        messages.append({"role": "user", "content": request.message})

        actions_taken: List[str] = []
        tools = _get_tools(allow_destructive)

        final_text = ""
        for _round in range(MAX_TOOL_ROUNDS):
            try:
                data = _call_ollama(messages, tools)
            except requests.exceptions.ConnectionError:
                return {
                    "success": False,
                    "error": (
                        f"Local AI (Ollama) isn't running on {OLLAMA_BASE_URL}. "
                        "Start Ollama and make sure it's reachable, then try again."
                    ),
                }
            except requests.exceptions.Timeout:
                return {
                    "success": False,
                    "error": f"Local AI (Ollama) timed out after {OLLAMA_TIMEOUT_SECONDS}s.",
                }
            except requests.exceptions.HTTPError as http_err:
                detail = ""
                try:
                    detail = http_err.response.text[:500]
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": f"Ollama returned an error: {http_err} {detail}".strip(),
                }

            message = data.get("message") or {}
            content = (message.get("content") or "").strip()
            tool_calls = message.get("tool_calls") or []

            if content:
                final_text = content

            if not tool_calls:
                # No tool calls - this is the model's final turn (or a small
                # local model that failed to produce tool-call format at all).
                break

            # Append the assistant's turn (with tool_calls) then execute every
            # tool call and feed results back as "tool" role messages.
            messages.append({
                "role": "assistant",
                "content": message.get("content", ""),
                "tool_calls": tool_calls,
            })

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {})
                # Ollama usually gives a dict already, but tolerate a JSON string.
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        raw_args = {}

                try:
                    result = _execute_tool(name, raw_args, db)
                    actions_taken.append(_summarize_result(name, result))
                except Exception as tool_err:
                    logger.error(f"Agent tool {name} failed: {tool_err}", exc_info=True)
                    result = {"error": str(tool_err)}
                    actions_taken.append(f"{name}: error - {tool_err}")

                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, default=str),
                })

        if not final_text:
            if actions_taken:
                final_text = (
                    "I performed the requested actions but didn't get a final summary back "
                    "from the local model. Here's what happened: " + "; ".join(actions_taken)
                )
            else:
                final_text = (
                    "I wasn't able to get a useful reply from the local AI model. This can "
                    "happen with small local models and tool-calling - try rephrasing, or "
                    "use the regular page buttons instead."
                )

        return {
            "success": True,
            "data": {
                "reply": final_text,
                "actions_taken": actions_taken,
            },
        }

    except Exception as e:
        logger.error(f"Agent chat failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
