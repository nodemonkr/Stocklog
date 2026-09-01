import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const mobileRoot = path.resolve(here, '..', 'src');
const backendRoot = path.resolve(here, '..', '..', 'backend', 'app');

function walk(dir, exts) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full, exts));
    else if (exts.some(ext => entry.name.endsWith(ext))) out.push(full);
  }
  return out;
}

function normalize(raw) {
  let s = String(raw || '').trim();
  s = s.replace(/\$\{[^}]+\}/g, '*');
  s = s.replace(/\{[^}/]+\}/g, '*');
  s = s.replace(/\?.*$/, '');
  s = s.replace(/\/+/g, '/');
  return s;
}

function extractApiStrings(text) {
  const found = new Set();
  const re = /([`'\"])(\/api\/[^`'\"\s]*)\1/g;
  for (const m of text.matchAll(re)) found.add(normalize(m[2]));
  // Template literals with embedded expressions are not matched by the simple quote regex above.
  const tpl = /`(\/api\/[^`]+)`/g;
  for (const m of text.matchAll(tpl)) found.add(normalize(m[1]));
  return found;
}

const mobile = new Set();
for (const file of walk(mobileRoot, ['.ts', '.tsx'])) {
  for (const p of extractApiStrings(fs.readFileSync(file, 'utf8'))) mobile.add(p);
}

const backend = new Set();
for (const file of walk(backendRoot, ['.py'])) {
  const text = fs.readFileSync(file, 'utf8');
  for (const m of text.matchAll(/['\"](\/api\/[^'\"\s]+)['\"]/g)) backend.add(normalize(m[1]));
}

function matches(pathname) {
  if (backend.has(pathname)) return true;
  const ps = pathname.split('/');
  return [...backend].some(route => {
    const rs = route.split('/');
    if (ps.length !== rs.length) return false;
    return ps.every((seg, i) => seg === rs[i] || seg === '*' || rs[i] === '*');
  });
}

const missing = [...mobile].filter(p => !matches(p)).sort();
console.log(`[AUDIT] Mobile API shapes: ${mobile.size}`);
console.log(`[AUDIT] Backend API shapes: ${backend.size}`);
if (missing.length) {
  console.error('[ERROR] Native mobile references API paths not found in backend source:');
  for (const p of missing) console.error(`  - ${p}`);
  process.exit(1);
}
console.log('[OK] Native mobile API references are backed by FastAPI source routes.');
