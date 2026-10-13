import * as pdfjs from './vendor/pdf.mjs';
import { parseStatement, layouts } from './core.mjs';
pdfjs.GlobalWorkerOptions.workerSrc = new URL('./vendor/pdf.worker.mjs', import.meta.url).href;
let ocrWorker = null;
let dotWorker = null;
let progressCallback = null;
const local = file => new URL(`./vendor/${file}`, import.meta.url).href;
async function getOCR(onProgress, dots = false) {
  progressCallback = onProgress;
  if (dots) {
    if (!dotWorker) {
      if (!globalThis.Tesseract) throw new Error('OCR library did not load.');
      let rejectInitialization;
      const reportedError = new Promise((_, reject) => { rejectInitialization = reject; });
      const creating = Tesseract.createWorker('eng', 0, {
        workerPath: new URL('./dot-matrix.worker.js', import.meta.url).href,
        workerBlobURL: false, corePath: local('tesseract-core'), langPath: local('legacy'),
        cachePath: 'hwfc-dot-matrix-v1', cacheMethod: 'write',
        logger: message => progressCallback?.(message),
        errorHandler: error => rejectInitialization(new Error(String(error))),
      });
      try {
        // Tesseract 6 can report a language/init failure without settling creating.
        // The local wrapper closes its worker; the error bridge settles our upload.
        dotWorker = await Promise.race([creating, reportedError]);
        await dotWorker.setParameters({ tessedit_pageseg_mode: Tesseract.PSM.SINGLE_BLOCK, preserve_interword_spaces: '1', user_defined_dpi: '400' });
      } catch (error) {
        dotWorker = null;
        creating.then(worker => worker.terminate()).catch(() => {});
        throw error;
      }
    }
    return dotWorker;
  }
  if (!ocrWorker) {
    if (!globalThis.Tesseract) throw new Error('OCR library did not load. Reload the app and try again.');
    ocrWorker = await Tesseract.createWorker('eng', 1, { workerPath: local('worker.min.js'), corePath: local('tesseract-core'), langPath: local('').replace(/\/$/, ''), logger: message => progressCallback?.(message), cacheMethod: 'write' });
    await ocrWorker.setParameters({ tessedit_pageseg_mode: Tesseract.PSM.AUTO, preserve_interword_spaces: '1', user_defined_dpi: '200' });
  }
  return ocrWorker;
}
export async function stopOCR() {
  const workers = [ocrWorker, dotWorker].filter(Boolean); ocrWorker = null; dotWorker = null;
  await Promise.all(workers.map(worker => worker.terminate()));
}
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
function joinDots(canvas, region, radius = 3) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const {left,top,width:w,height:h} = region;
  const image = ctx.getImageData(left, top, w, h);
  const gray = new Uint8Array(w*h), horizontal = new Float32Array(w*h), span = radius*2+1;
  for (let n=0;n<gray.length;n++) {
    const i=n*4, value=.299*image.data[i]+.587*image.data[i+1]+.114*image.data[i+2];
    // Recover faint colored dot-matrix ink before connecting its broken strokes.
    gray[n]=value>225?255:0;
  }
  for (let y=0;y<h;y++) {
    let sum=0;
    for(let dx=-radius;dx<=radius;dx++)sum+=gray[y*w+Math.max(0,Math.min(w-1,dx))];
    for(let x=0;x<w;x++) {
      horizontal[y*w+x]=sum/span;
      sum+=gray[y*w+Math.min(w-1,x+radius+1)]-gray[y*w+Math.max(0,x-radius)];
    }
  }
  for (let x=0;x<w;x++) {
    let sum=0;
    for(let dy=-radius;dy<=radius;dy++)sum+=horizontal[Math.max(0,Math.min(h-1,dy))*w+x];
    for(let y=0;y<h;y++) {
      const i=(y*w+x)*4, value=sum/span>180?255:0;
      image.data[i]=image.data[i+1]=image.data[i+2]=value;
      sum+=horizontal[Math.min(h-1,y+radius+1)*w+x]-horizontal[Math.max(0,y-radius)*w+x];
    }
  }
  ctx.putImageData(image,left,top);
}
function scanQuality(lines, filename, ocrFields) {
  const doc=parseStatement([{page:1,lines,ocr:true,ocrFields}],filename);
  const valid=doc.rows.filter(row=>row.invoiceNumber && row.date);
  const agrees=doc.declaredTotal!=null && doc.rows.reduce((sum,row)=>sum+row.amount,0)===doc.declaredTotal;
  return {doc, score:valid.length*100 + doc.rows.length*10 + (agrees?20:0) + (doc.statementDate?5:0) + (doc.declaredTotal!=null?5:0)};
}
async function retryScan(page, initial, filename, report) {
  const quality=scanQuality(initial,filename), doc=quality.doc;
  if (doc.rows.length && doc.statementDate && doc.declaredTotal!=null && doc.rows.every(row=>row.confidence>=80 && row.date)) return {lines:initial};
  const rinella=layouts.find(layout=>layout.id==='rinella').pattern.test(initial.map(line=>line.text).join('\n'));
  if (!rinella && doc.rows.length) return {lines:initial};
  const scaled=page.getViewport({scale:(rinella?400:300)/72});
  const canvas=documentCanvas(scaled);
  try {
    report('Reading scan more closely');
    await page.render({canvasContext:canvas.getContext('2d'),viewport:scaled}).promise;
    let candidate, ocrFields;
    if (rinella) {
      const header=initial.find(line=>/\bdate\b/i.test(line.text) && /\binvoice\b/i.test(line.text) && /\bamount\b/i.test(line.text) && /\bbalance\b/i.test(line.text));
      const dateLabel=initial.flatMap(line=>line.words??[]).find(word=>/^date:?$/i.test(word.text) && word.y<.35 && word.x>.5) ?? {x:.62,y:.225};
      // These regions belong to the independently identified vendor template;
      // missing OCR headings do not mean the invoice table is missing.
      const headerY=header?.y ?? .39;
      const rect=(left,top,right,bottom)=>({left:Math.round(left*canvas.width),top:Math.round(top*canvas.height),width:Math.round((right-left)*canvas.width),height:Math.round((bottom-top)*canvas.height)});
      const regions=[rect(.13,headerY+.015,.97,.77),rect(Math.max(.5,dateLabel.x-.05),dateLabel.y-.012,Math.min(.73,dateLabel.x+.1),dateLabel.y+.065),rect(.74,.778,.98,.83)];
      const worker=await getOCR(()=>{},true);
      const words=initial.flatMap(line=>line.words??[]).filter(word=>!regions.some(r=>word.x*canvas.width>=r.left && word.x*canvas.width<r.left+r.width && word.y*canvas.height>=r.top && word.y*canvas.height<r.top+r.height));
      ocrFields={};
      for (const [index,region] of regions.entries()) {
        joinDots(canvas,region);
        const {data}=await worker.recognize(canvas,{rectangle:region},{text:true,tsv:true});
        words.push(...tsvWords(data.tsv,canvas.width,canvas.height));
        if(index===1)ocrFields.statementDate={text:data.text||'',confidence:data.confidence??0};
        if(index===2)ocrFields.printedTotal={text:data.text||'',confidence:data.confidence??0};
      }
      candidate=wordsToLines(words,.005);
    } else {
      const worker=await getOCR(()=>{});
      const {data}=await worker.recognize(canvas,{}, {text:true,tsv:true});
      candidate=wordsToLines(tsvWords(data.tsv,canvas.width,canvas.height),.005);
    }
    if (scanQuality(candidate,filename,ocrFields).score>quality.score) return {lines:candidate,ocrFields,note:'Enhanced scan reading was used. Verify every invoice number and amount against the PDF before confirming.'};
    return {lines:initial,note:'Enhanced scan reading could not recover clearer values. Review the PDF and correct any unreadable fields manually.'};
  } catch(error) {
    return {lines:initial,note:'Enhanced scan retry was unavailable. The initial extraction was retained; review unreadable fields against the PDF.'};
  } finally {canvas.width=0;canvas.height=0;}
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
    const pages = [], scanNotes = [];
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
      let lines, ocrFields, ocr = false;
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
        const retry=await retryScan(page,lines,file.name,stage=>onProgress({page:index,total:document.numPages,stage,fraction:(index-.1)/document.numPages}));
        lines=retry.lines;
        ocrFields=retry.ocrFields;
        if(retry.note)scanNotes.push(`Page ${index}: ${retry.note}`);
      } else lines = wordsToLines(words, .004);
      pages.push({ page: index, lines, ocr, ocrFields });
      page.cleanup();
    }
    onProgress({ page: document.numPages, total: document.numPages, stage: 'Ready for review', fraction: 1 });
    const statement = parseStatement(pages, file.name);
    statement.warnings.push(...scanNotes);
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
