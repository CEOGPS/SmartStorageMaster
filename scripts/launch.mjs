#!/usr/bin/env node
// One-command launcher: starts the backend and the web UI, waits until both are
// healthy, then opens the app (browser by default, Electron with --desktop).
//
//   node scripts/launch.mjs              open in the browser
//   node scripts/launch.mjs --desktop    open in the Electron window
//   node scripts/launch.mjs --no-open    just start the servers
//
// Ctrl+C (or closing the Electron window) stops everything it started.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import http from 'node:http';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BACKEND = path.join(ROOT, 'backend');
const FRONTEND = path.join(ROOT, 'frontend');
const API_PORT = 8000;
const WEB_PORT = 3000;
const IS_WIN = process.platform === 'win32';
const args = new Set(process.argv.slice(2));
const children = [];
let shuttingDown = false;

const c = (code, s) => (process.stdout.isTTY ? `\x1b[${code}m${s}\x1b[0m` : s);
const say = (s) => console.log(`${c(35, '[launch]')} ${s}`);
class Stop extends Error {}
// Report, stop everything already started, and halt the launch sequence so
// nothing new gets started after an error.
const fail = (s) => {
  if (!shuttingDown) console.error(`${c(31, '[launch] ERROR:')} ${s}`);
  shutdown(1);
  throw new Stop(s);
};

function run(cmd, cmdArgs, opts = {}) {
  return spawnSync(cmd, cmdArgs, { stdio: 'pipe', encoding: 'utf8', shell: IS_WIN && opts.shell, ...opts });
}

function findPython() {
  const candidates = IS_WIN ? [['py', ['-3']], ['python', []], ['python3', []]] : [['python3', []], ['python', []]];
  for (const [cmd, pre] of candidates) {
    const r = run(cmd, [...pre, '-c', 'import sys; print(sys.version_info[:2] >= (3, 9))']);
    if (r.status === 0 && r.stdout.trim() === 'True') return { cmd, pre };
  }
  return null;
}

function portFree(port) {
  return new Promise((resolve) => {
    const s = net.createServer().once('error', () => resolve(false)).once('listening', () => s.close(() => resolve(true)));
    s.listen(port, '127.0.0.1');
  });
}

function waitFor(url, label, timeoutMs = 90000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tryOnce = () => {
      http.get(url, (res) => { res.resume(); resolve(); })
        .on('error', () => {
          if (Date.now() - start > timeoutMs) reject(new Error(`${label} did not start within ${timeoutMs / 1000}s`));
          else setTimeout(tryOnce, 500);
        });
    };
    tryOnce();
  });
}

function start(name, colorCode, cmd, cmdArgs, opts) {
  if (shuttingDown) throw new Stop('shutting down');
  // Own process group on macOS/Linux so shutdown can stop the whole tree
  // (e.g. a tool and anything it spawned), not just the direct child.
  const child = spawn(cmd, cmdArgs, { stdio: ['ignore', 'pipe', 'pipe'], detached: !IS_WIN, ...opts, shell: IS_WIN && !!opts?.shell });
  const tag = c(colorCode, `[${name}]`);
  const pipe = (stream) => stream.on('data', (d) => String(d).split(/\r?\n/).filter(Boolean).forEach((l) => console.log(`${tag} ${l}`)));
  pipe(child.stdout); pipe(child.stderr);
  child.on('exit', (code, signal) => {
    if (shuttingDown) return;
    try { fail(`${name} stopped unexpectedly (${signal ? `signal ${signal}` : `exit code ${code}`}). See the output above.`); } catch { /* reported */ }
  });
  child.detachedGroup = !IS_WIN;
  children.push(child);
  return child;
}

function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  say('Stopping...');
  for (const ch of children) {
    if (!ch.pid || ch.exitCode !== null) continue;
    try {
      if (IS_WIN) spawnSync('taskkill', ['/pid', String(ch.pid), '/T', '/F']);
      else if (ch.spawnargs && ch.detachedGroup) process.kill(-ch.pid, 'SIGTERM');
      else ch.kill('SIGTERM');
    } catch { /* already gone */ }
  }
  setTimeout(() => process.exit(code), 400);
}
process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

async function main() {
  say('Storage Manager Pro');

  // 1. Prerequisites
  const py = findPython();
  if (!py) fail('Python 3.9+ was not found. Install it from https://www.python.org/downloads/ (tick "Add Python to PATH") and run this again.');
  if (!existsSync(path.join(BACKEND, 'run.py'))) fail(`Cannot find backend/run.py. Run this from the project folder (${ROOT}).`);

  // 2. First-run installs (skipped when already present)
  if (run(py.cmd, [...py.pre, '-c', 'import fastapi, uvicorn, sqlalchemy, blake3']).status !== 0) {
    say('Installing backend packages (first run only, this can take a few minutes)...');
    const r = spawnSync(py.cmd, [...py.pre, '-m', 'pip', 'install', '-r', path.join(BACKEND, 'requirements.txt')], { stdio: 'inherit' });
    if (r.status !== 0) fail('Backend packages failed to install. See the output above.');
  }
  if (!existsSync(path.join(FRONTEND, 'node_modules'))) {
    say('Installing frontend packages (first run only)...');
    const r = spawnSync('npm', ['install', '--no-audit', '--no-fund'], { cwd: FRONTEND, stdio: 'inherit', shell: IS_WIN });
    if (r.status !== 0) fail('Frontend packages failed to install. See the output above.');
  }

  // 3. Ports
  for (const [port, what] of [[API_PORT, 'backend'], [WEB_PORT, 'web UI']]) {
    if (!(await portFree(port))) fail(`Port ${port} (${what}) is already in use. Close the other copy of the app and try again.`);
  }

  // 4. Start. The backend listens on 127.0.0.1 only: it can move and delete files,
  //    so it must not be reachable from other machines on the network.
  say('Starting backend...');
  start('api', 36, py.cmd, [...py.pre, 'run.py', '--host', '127.0.0.1', '--port', String(API_PORT)], { cwd: BACKEND });
  try { await waitFor(`http://127.0.0.1:${API_PORT}/docs`, 'Backend'); } catch (e) { fail(e.message); }
  say('Backend ready.');

  say('Starting web UI...');
  const viteBin = path.join(FRONTEND, 'node_modules', '.bin', IS_WIN ? 'vite.cmd' : 'vite');
  start('web', 33, viteBin, ['--port', String(WEB_PORT), '--strictPort', '--host', '127.0.0.1'], { cwd: FRONTEND, shell: true });
  try { await waitFor(`http://127.0.0.1:${WEB_PORT}/`, 'Web UI'); } catch (e) { fail(e.message); }

  const url = `http://localhost:${WEB_PORT}`;
  say(`${c(32, 'Ready')}: ${url}   (Ctrl+C to stop)`);

  // 5. Open
  if (args.has('--no-open')) return;
  if (args.has('--desktop')) {
    const electron = path.join(ROOT, 'node_modules', '.bin', IS_WIN ? 'electron.cmd' : 'electron');
    if (!existsSync(electron)) { say('Electron is not installed (run "npm install" in the project root). Opening the browser instead.'); }
    else {
      const ch = spawn(electron, ['.'], { cwd: ROOT, stdio: 'inherit', shell: IS_WIN });
      children.push(ch);
      ch.on('exit', () => shutdown(0)); // closing the window stops the servers
      return;
    }
  }
  const opener = IS_WIN ? ['cmd', ['/c', 'start', '', url]] : process.platform === 'darwin' ? ['open', [url]] : ['xdg-open', [url]];
  spawn(opener[0], opener[1], { stdio: 'ignore', detached: true }).on('error', () => say(`Open ${url} in your browser.`)).unref();
}

main().catch((e) => {
  if (e instanceof Stop) return;
  try { fail(e.message); } catch { /* reported */ }
});
