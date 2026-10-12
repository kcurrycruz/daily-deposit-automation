import { cp, mkdir, readdir, realpath, readFile, writeFile, stat } from 'node:fs/promises';
import { resolve, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

const root = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(root, 'frontend');
const vendor = resolve(frontend, 'vendor');
const require = createRequire(import.meta.url);
const packageDir = name => dirname(require.resolve(name + '/package.json'));
await mkdir(resolve(vendor, 'licenses'), { recursive: true });
for (const [from, to] of [
  ['pdfjs-dist/build/pdf.mjs', 'pdf.mjs'],
  ['pdfjs-dist/build/pdf.worker.mjs', 'pdf.worker.mjs'],
  ['tesseract.js/dist/tesseract.min.js', 'tesseract.min.js'],
  ['tesseract.js/dist/worker.min.js', 'worker.min.js'],
  ['@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz', 'eng.traineddata.gz'],
]) await cp(resolve(root, 'node_modules', from), resolve(vendor, to));
const tesseractRequire = createRequire(await realpath(resolve(packageDir('tesseract.js'), 'package.json')));
const core = dirname(tesseractRequire.resolve('tesseract.js-core/package.json'));
await mkdir(resolve(vendor, 'tesseract-core'), { recursive: true });
for (const name of await readdir(core)) {
  if (/\.(?:js|wasm)$/.test(name)) await cp(resolve(core, name), resolve(vendor, 'tesseract-core', name));
}
const result = await build({
  absWorkingDir: root, entryPoints: ['streamlit_bridge.mjs'], bundle: true,
  format: 'esm', platform: 'browser', minify: true, legalComments: 'inline',
  outfile: resolve(frontend, 'bridge.bundle.mjs'), metafile: true,
});
const packages = new Map([
  ['pdfjs-dist', packageDir('pdfjs-dist')], ['tesseract.js', packageDir('tesseract.js')],
  ['tesseract.js-core', core], ['eng', packageDir('@tesseract.js-data/eng')],
  ['streamlit-component-lib', packageDir('streamlit-component-lib')],
]);
for (const input of Object.keys(result.metafile.inputs)) {
  let path = dirname(resolve(root, input));
  while (path !== dirname(path)) {
    try {
      const info = JSON.parse(await readFile(resolve(path, 'package.json'), 'utf8'));
      if (path.includes('node_modules') && info.name) packages.set(info.name.replaceAll('/', '__'), path);
      break;
    } catch { path = dirname(path); }
  }
}
for (const [name, path] of packages) {
  const licenses = (await readdir(path)).filter(f => /^(?:licen[cs]e|notice|copying)(?:\.|$)/i.test(f));
  let text = '';
  for (const file of licenses) if ((await stat(resolve(path, file))).isFile()) text += await readFile(resolve(path, file), 'utf8') + '\n';
  if (!text && ['eng', 'streamlit-component-lib'].includes(name)) text = await readFile(resolve(root, 'licenses', name + '.txt'), 'utf8');
  if (!text) throw new Error('Missing license for bundled package ' + name);
  await writeFile(resolve(vendor, 'licenses', name + '.txt'), text);
}
console.log('Local PDF, OCR, Streamlit bridge, and license assets prepared.');
