# SmartStorageMaster: handoff (bugs, safety, consolidation, redesign)

Owner: Chris (CEOGPS). Repo: `CEOGPS/SmartStorageMaster`, branch `main`.
Prereq: PR #4 (promote worktree code to root) is merged. PR #3 is superseded by it; close it or rebase it.
Working style: the owner wants concise updates, one step at a time, and suggestions for improvement.
Do not change the color scheme. Use `CEOGPS/CEOLife` as a read-only reference for spacing, cards, typography and motion.

## 0. Order of work (ship as separate PRs)

1. **Phase 1: bug fixes** (section 1). Small, independent, merge first.
2. **Phase 2: protected folders and projects** (section 2) and **duplicate-choice rules** (section 3).
3. **Phase 3: speed** (section 4).
4. **Phase 4: consolidation to one process plus Cloudflare services** (section 5). Hold until the owner confirms the architecture (see the decision note there).
5. **Phase 5: redesign, avatar and AI dock** (section 6).

Every phase: run the app, verify in a browser, and state what you did not test.

## 1. Bugs reported by the owner (verified against the code)

| # | Symptom | Finding | Fix |
|---|---------|---------|-----|
| 1.1 | Organizer buttons show weird symbols | `frontend/src/components/FileOrganizer/FileOrganizer.jsx` (around lines 39-43) has mojibake saved in the source, e.g. `icon: 'ð'`. The emoji were double-encoded at some point. HTML is already `charset=UTF-8`. | Replace every garbled literal with real emoji or, better, inline SVG icons. Grep all of `frontend/src` for `[^\x00-\x7F]` and fix any other garbled strings. Save files as UTF-8. |
| 1.2 | Eye icon does nothing (it should show a thumbnail) | `DuplicateViewer.jsx` (around line 190): the eye and the folder button have no `onClick`. Backend `GET /organizer/thumbnail/{file_id}` exists and streams the file. | Wire the eye to a preview modal: image, video and PDF first-page where possible, a file-type icon otherwise. Wire the folder button to reveal the file in the OS (Electron `shell.showItemInFolder` via `preload.js`). Add a tooltip that says what each icon does. |
| 1.3 | Delete does not work | Flow: `handleCleanup` calls `selectForCleanup` (backup, then `DELETE /cleanup/delete`). Cannot be reproduced from here. Strong suspect: stale index rows whose paths were stored malformed by the old scanner (`D:folder\file` with no backslash after the drive letter), so the file cannot be found on disk. Check the backend logs for the real error. | Reproduce first. Run the one-off cleanup of malformed rows (`DELETE FROM files WHERE path GLOB '[A-Za-z]:[^\]*'`), rescan, retry. Then surface per-file errors in the UI (today failures are swallowed into a generic alert). Delete should go to the Recycle Bin by default (`send2trash`), with permanent delete as an explicit option. |
| 1.3b | Duplicate delete UX | `confirm()`/`alert()` dialogs. | Use the existing `ConfirmModal`, show per-file results, and offer undo through the backup/restore feature. |
| 1.4 | Organizer page: files do not load | Cannot be reproduced from here. Endpoint `GET /organizer/files` exists. Likely the same stale-path rows, or a response-shape mismatch in `listOrganizerFiles`. | Reproduce in the browser, read the network tab, fix the root cause, and add an empty state and an error state so it never fails silently. |
| 1.5 | Scan WebSocket 404 | Backend lacked a WebSocket library. | Make `requirements.txt` require `uvicorn[standard]` (already listed). Add a startup self-check that warns clearly if the WebSocket route is unavailable. |
| 1.6 | Scan is very slow | See section 4. | |

## 2. Protected folders and projects ("lock")

Problem: scans index project internals (`package.json`, `.env`, `node_modules`, `.git`, `venv`) and offer them for dedupe or cleanup. Deleting or moving these breaks projects.

Requirements:
- **Project detection.** A folder is a *project root* if it contains any marker: `.git`, `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, `pom.xml`, `*.sln`, `*.csproj`, `composer.json`, `Gemfile`, `.vscode`, `.idea`. Everything under a project root is *project content*.
- **Locks.** New table `protected_paths(id, path, kind {project|folder|file}, source {auto|user}, created_at, note)`. Auto-detected projects are locked by default; the user can unlock one. The user can lock any folder from the Scan page, the Organizer and a context menu. Locks apply to descendants.
- **Enforcement lives in the backend, not just the UI.** Delete, move, organize and the agent's tools must all refuse locked paths and return a clear reason. The agent must not be able to bypass locks.
- **Scan behavior.** Offer three modes per scan: (a) skip project folders entirely (default), (b) index but mark as protected (read-only, visible in analytics, never actionable), (c) include as normal (requires an explicit confirmation). Always skip `node_modules`, `.git`, `venv`, `__pycache__`, `$RECYCLE.BIN`, `System Volume Information`.
- **Secrets.** Never hash, preview or display the contents of `.env*`, key files (`*.pem`, `id_rsa*`) or credential files. Index name and size only, and mark them protected.
- **UI.** Lock badge on rows, a "Protected" page listing locks with an unlock action, and a lock toggle in the scan and organizer UIs.
- The "Skip system folders" checkbox on the Scan page and its siblings are currently unwired (uncontrolled checkboxes). Make every scan option a real, persisted setting sent to the backend.

## 3. Duplicate review: the user chooses what to delete

Problem: the app auto-picks a "primary" (`is_primary = idx == 0` in `duplicate_service.py`) and refuses to let the user delete it. Often the primary is a stray file and the copy inside a project is the one offered for deletion.

Requirements:
- **Any copy can be the keeper.** Remove the hard lock on the primary. Each group has "Keep this one" per file; everything else becomes deletable.
- **Smart default, never forced.** Suggest the keeper by rules the user can reorder: file inside a protected project wins; shorter path depth; named folder over Downloads/Desktop; oldest created. Show why (a small "suggested because" chip).
- **Project-safety rules.** A copy inside a protected project can never be selected for deletion. If the suggested keeper is outside a project but a copy is inside one, the UI must say so and keep the project copy by default.
- **Bulk actions.** "Keep newest", "keep shortest path", "keep inside project", per group and across all groups, with a preview of how many bytes will be freed before anything runs.
- Side-by-side comparison with the preview from 1.2 (thumbnails, size, dates, full path).

## 4. Scan speed

The scanner already uses `os.scandir`, 1 MiB reads, bulk DB writes and hash reuse for unchanged files. The bottleneck is reading every byte of every file to compute both MD5 and SHA-256.

- **Stage 1:** walk and record size and mtime only (fast, progress is accurate).
- **Stage 2:** hash only files that share a size with another file. Unique sizes cannot be exact duplicates.
- Use one hash (BLAKE2b or MD5) instead of two. Keep SHA-256 only if a feature truly needs it.
- Optional prefilter: hash first 64 KB, then do a full hash only when prefixes match.
- Hash on a thread pool (`hashlib` releases the GIL on large buffers). Cap workers to avoid thrashing spinning disks, and expose a setting.
- Skip project and excluded folders (section 2) before doing any work.
- Make scans cancellable and resumable, and show real progress (stage, files, bytes, ETA).

## 5. Consolidation: one app instead of three servers (decision needed)

Today: Vite dev server, a Python/FastAPI backend, and an Electron shell, plus Ollama for the LLM. The owner wants this simplified and wants to use Cloudflare Workers.

**Important constraint:** a Cloudflare Worker cannot read the user's local disk. File scanning, hashing, moving and deleting must run on the user's machine. So Workers cannot replace the scanner, but they can replace almost everything else.

Recommended architecture:
- **One local process: Electron.** The main process does scanning, hashing (worker threads), SQLite (`better-sqlite3`), locks and file operations. The UI loads from built static files, with no Vite server in production and no separate backend server. Expose a typed IPC API through `preload.js`. One command to run, one installer to ship.
- **Cloudflare Workers AI replaces Ollama.** A small Worker is the AI gateway: the agent calls it for chat and tool planning. No local model to install. Keep the API key in the Worker, never in the app. Rate-limit per install.
- **Optional, only if needed:** D1 for settings/sync across devices, R2 for cached thumbnails or backups, Durable Objects for agent conversation state. Do not add any of these unless a feature requires them.
- **Privacy rule:** only send file *metadata the user approves* (names, sizes, folder structure) to the Worker. Never send file contents or locked paths.
- Migration path: port the backend logic to Node in stages behind the same API shape, delete the Python backend last, and keep the tests passing throughout.

If the owner prefers to keep Python, the fallback is: Electron spawns the Python backend as a hidden child process (one visible app, no separate terminals), with the Worker still replacing Ollama.

**Ask the owner to confirm this architecture before starting Phase 4.** Phases 1-3 do not depend on it.

## 6. Redesign, agent avatar and AI dock

- Keep the existing color scheme. Match CEOLife's spacing, card styling, type scale and motion.
- Streamline navigation. Today there are seven pages; merge Duplicates and Cleanup into a single "Review" flow, and make Scan, Review, Organize, Protected and Settings the core. Dashboard becomes a clean summary with one primary action.
- Replace emoji icons with one consistent icon set (inline SVG).
- Responsive layouts, keyboard navigation, focus rings, `prefers-reduced-motion`, and WCAG AA contrast.
- **Agent avatar.** `AgentAvatar.jsx` exists. Give it states: idle, listening, thinking, working (with the current tool), done, error. Subtle animation with a reduced-motion fallback.
- **AI dock.** A dock that docks to any edge, collapses to the avatar, resizes, and remembers position. Contains: chat, suggested actions based on the current page ("Review 42 duplicates", "Lock this project"), a live activity feed of what the agent is doing, and an approval step for any destructive action (the agent proposes, the user confirms, locks are always enforced).
- Agent safety: it can plan and propose; deletes and moves require explicit user approval in the UI.

## 7. Repo hygiene and quality gates

- `.claude/`, `.impeccable/`, `*.exe`, `*.log` are ignored (done in PR #4). Never commit installers or worktrees.
- Add a GitHub Action that runs backend tests and the frontend build on every PR. The repo currently has no CI.
- `launch.json`-style files must not contain personal absolute paths.
- Update `README.md` to describe the real architecture and how to run it in one command.

## 8. Acceptance checklist

- [ ] Scanning `D:\` finishes without a UNIQUE error, skips projects by default, and is visibly faster.
- [ ] Locking a folder blocks delete, move, organize and agent actions on it, enforced in the backend.
- [ ] In duplicates, the user can keep any copy; project copies are never offered for deletion.
- [ ] Eye opens a working preview; folder button reveals the file in Explorer.
- [ ] Delete works, goes to the Recycle Bin, shows per-file results, and is undoable.
- [ ] Organizer icons render correctly and files load, with empty and error states.
- [ ] No Ollama; the app runs from a single launch command.
- [ ] Redesign and dock pass a mobile-width and keyboard-only check.
