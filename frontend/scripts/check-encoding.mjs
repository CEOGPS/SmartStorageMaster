// Fails if any source file contains "mojibake" (UTF-8 text that was saved or
// copied through the wrong encoding, e.g. an emoji turned into "ð..." characters).
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const BAD = /[Â-ô][\u0080-¿]|�/;
const EXT = /\.(jsx?|css|html|json|md)$/;
let failures = 0;

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { if (name !== 'node_modules' && name !== 'dist') walk(p); continue; }
    if (!EXT.test(name)) continue;
    readFileSync(p, 'utf8').split('\n').forEach((line, i) => {
      if (BAD.test(line)) { failures++; console.error(`${p}:${i + 1}: garbled characters`); }
    });
  }
}

walk(new URL('..', import.meta.url).pathname.replace(/\/$/, '') + '/src');
walk(new URL('..', import.meta.url).pathname.replace(/\/$/, '') + '/public');
if (failures) { console.error(`\n${failures} line(s) with garbled characters.`); process.exit(1); }
console.log('Encoding check passed.');
