import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', 'src');
const allowedWeights = new Set([
  'normal', 'bold',
  '100', '200', '300', '400', '500', '600', '700', '800', '900',
  'ultralight', 'thin', 'light', 'medium', 'regular', 'semibold', 'condensedBold', 'condensed', 'heavy', 'black',
]);
const errors = [];

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(full);
      continue;
    }
    if (!/\.(ts|tsx)$/.test(entry.name)) continue;
    const source = fs.readFileSync(full, 'utf8');
    const rel = path.relative(path.resolve(here, '..'), full);
    for (const match of source.matchAll(/fontWeight\s*:\s*['"]([^'"]+)['"]/g)) {
      const value = match[1];
      if (!allowedWeights.has(value)) {
        const line = source.slice(0, match.index).split('\n').length;
        errors.push(`${rel}:${line} unsupported fontWeight '${value}'`);
      }
    }
    if (/react-native-webview|STOCKLOG_WEB_HTML|stocklog-bundle/.test(source)) {
      errors.push(`${rel}: WebView-era runtime reference found in native app source`);
    }
  }
}

walk(root);
if (errors.length) {
  console.error('[ERROR] Native style/runtime validation failed:');
  for (const error of errors) console.error(`  - ${error}`);
  process.exit(1);
}
console.log('[OK] Native style/runtime literals are valid.');
