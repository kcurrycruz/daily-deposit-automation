import * as pdfjs from './vendor/pdf.mjs';
import { parseStatement } from './core.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.mjs', import.meta.url).href;
let ocrWorker = null;
let progressCallback = null;
const local = file => new URL(`./vendor/${file}`, import.meta.url).href;
async function getOCR(onProgress) {
  progressCallback = onProgress;
  if (!ocrWorker) {
    if (!globalThis.Tesseract) throw new Error('OCR library did not load. Reload the app and try again.');
    ocrWorker = await Tesseract.createWorker('eng', 1, { workerPath: local('worker.min.js'), corePath: local('tesseract-core'), langPath: local('').replace(/\/$/, ''), logger: message => progressCallback?.(message), cacheMethod: 'write' });
    await ocrWorker.setParameters({ tessedit_pageseg_mode: Tesseract.PSM.AUTO, preserve_interword_spaces: '1', user_defined_dpi: '200' });
  }
  return ocrWorker;
}
export async function stopOCR() { if (ocrWorker) await ocrWorker.terminate(); ocrWorker = null; }
export function wordsToLines(words, tolerance = .006) {
  const groups = [];
  for (const word of words.sort((a, b) => a.y - b.y || a.x - b.x)) {
    if (!word.text.trim()) continue;
    let group = groups.find(g => Math.abs(g.y - word.y) < tolerance);
    if (!group) { group = { y: word.y, words: [] }; groups.push(group); }
    group.words.push(word);
  }
  return groups.sort((a, b) => a.y - b.y).map(g => {
    const sorted = g.words.sort((a, b) => a.x - b.x);
    return { text: sorted.map(w => w.text).join(' ').replace(/\s+/g, ' '), y: g.y, words: sorted, confidence: Math.min(...sorted.map(w => w.confidence ?? 99)) };
  });
}
function tsvWords(tsv, width, height) {
  return (tsv || '').split('\n').slice(1).flatMap(line => {
    const parts = line.split('\t');
    if (parts.length < 12 || parts[0] !== '5' || !parts.slice(11).join('\t').trim()) return [];
    return [{ text: parts.slice(11).join('\t'), x: Number(parts[6]) / width, y: (Number(parts[7]) + Number(parts[9]) / 2) / height, width: Number(parts[8]) / width, confidence: Math.max(0, Number(parts[10])) }];
  });
}
function improveScan(canvas) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < image.data.length; i += 4) {
    const luminance = .299 * image.data[i] + .587 * image.data[i+1] + .114 * image.data[i+2];
    const gray = luminance > 175 ? 255 : luminance < 60 ? 0 : Math.round((luminance - 60) * 255 / 115);
    image.data[i] = image.data[i+1] = image.data[i+2] = gray;
  }
  ctx.putImageData(image, 0, 0);
}
function tableSkew(words, width, height) {
  const left = words.find(w => /^trans\.?$/i.test(w.text) && w.x < .18 && w.y < .5);
  const right = words.find(w => /^balance$/i.test(w.text) && w.x > .7 && left && Math.abs(w.y - left.y) < .04);
  if (!left || !right) return 0;
  return Math.atan((right.y - left.y) * height / ((right.x - left.x) * width));
}
function straighten(canvas, angle) {
  const copy = documentCanvas({ width: canvas.width, height: canvas.height });
  const ctx = copy.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, copy.width, copy.height);
  ctx.translate(copy.width/2, copy.height/2); ctx.rotate(-angle); ctx.drawImage(canvas, -canvas.width/2, -canvas.height/2);
  const target = canvas.getContext('2d'); target.clearRect(0, 0, canvas.width, canvas.height); target.drawImage(copy, 0, 0); copy.width = 0; copy.height = 0;
}
export async function extractPDF(file, onProgress = () => {}) {
  if (file.size > 50 * 1024 * 1024) throw new Error('This PDF is larger than 50 MB. Split or compress it before uploading.');
  const bytes = new Uint8Array(await file.arrayBuffer());
  const document = await pdfjs.getDocument({ data: bytes, useSystemFonts: true }).promise;
  try {
    if (document.numPages > 100) throw new Error('This PDF has more than 100 pages. Split it into smaller statements.');
    const pages = [];
    for (let index = 1; index <= document.numPages; index++) {
      onProgress({ page: index, total: document.numPages, stage: 'Reading text', fraction: (index - 1) / document.numPages });
      const page = await document.getPage(index);
      const viewport = page.getViewport({ scale: 1 });
      const content = await page.getTextContent();
      const words = content.items.filter(item => item.str?.trim()).flatMap(item => {
        const transform = pdfjs.Util.transform(viewport.transform, item.transform);
        const tokens = item.str.match(/\S+/g) ?? [];
        let offset = 0;
        return tokens.map(text => {
          const at = item.str.indexOf(text, offset); offset = at + text.length;
          return { text, x: (transform[4] + item.width * at / Math.max(item.str.length, 1)) / viewport.width, y: (transform[5] - Math.abs(transform[3]) * .3) / viewport.height, width: item.width * text.length / Math.max(item.str.length, 1) / viewport.width, confidence: 99 };
        });
      });
      let lines, ocr = false;
      if (words.map(w => w.text).join(' ').length < 60) {
        ocr = true;
        const scaled = page.getViewport({ scale: 200 / 72 });
        const canvas = documentCanvas(scaled);
        await page.render({ canvasContext: canvas.getContext('2d'), viewport: scaled }).promise;
        improveScan(canvas);
        const worker = await getOCR(message => onProgress({ page: index, total: document.numPages, stage: message.status === 'recognizing text' ? `OCR ${Math.round(message.progress * 100)}%` : 'Preparing OCR', fraction: (index - 1 + (message.progress || 0) * .9) / document.numPages }));
        let { data } = await worker.recognize(canvas, {}, { text: true, tsv: true });
        let recognized = tsvWords(data.tsv, canvas.width, canvas.height);
        const angle = tableSkew(recognized, canvas.width, canvas.height);
        if (Math.abs(angle) > .0035 && Math.abs(angle) < .0524) {
          onProgress({ page: index, total: document.numPages, stage: 'Straightening scanned table', fraction: (index-.2)/document.numPages });
          straighten(canvas, angle);
          ({ data } = await worker.recognize(canvas, {}, { text: true, tsv: true }));
          recognized = tsvWords(data.tsv, canvas.width, canvas.height);
        }
        lines = wordsToLines(recognized, .005);
        if (!lines.length) lines = (data.text || '').split('\n').filter(Boolean).map((text, i, all) => ({ text, y: i / all.length, words: [], confidence: data.confidence ?? 0 }));
        canvas.width = 0; canvas.height = 0;
      } else lines = wordsToLines(words, .004);
      pages.push({ page: index, lines, ocr });
      page.cleanup();
    }
    onProgress({ page: document.numPages, total: document.numPages, stage: 'Ready for review', fraction: 1 });
    const statement = parseStatement(pages, file.name);
    statement.rawText = pages.map(p => `PAGE ${p.page}\n${p.lines.map(l => l.text).join('\n')}`).join('\n\n');
    return statement;
  } finally { await document.destroy(); }
}
function documentCanvas(viewport) {
  const canvas = globalThis.document.createElement('canvas'); canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height); return canvas;
}
export async function renderPage(file, number, canvas) {
  const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()), useSystemFonts: true }).promise;
  try {
    const page = await doc.getPage(Math.min(number, doc.numPages));
    const viewport = page.getViewport({ scale: 1.3 });
    canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
  } finally { await doc.destroy(); }
}
