export const money = cents => cents == null ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100);
export function cents(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? Math.round(value * 100) : null;
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const negative = raw.includes('-') || raw.includes('(');
  const clean = raw.replace(/[$,()\s+-]/g, '');
  if (!/^\d+(?:\.\d{1,2})?$/.test(clean)) return null;
  const [whole, decimal = ''] = clean.split('.');
  return (Number(whole) * 100 + Number(decimal.padEnd(2, '0'))) * (negative ? -1 : 1);
}
export const invoiceKey = value => String(value ?? '').trim().toUpperCase().replace(/\s+/g, '');
export const vendorKey = value => String(value ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
export const uid = () => globalThis.crypto?.randomUUID?.() ?? `r${Date.now()}${Math.random().toString(36).slice(2)}`;
const datePattern = /\b\d{1,2}\/\d{1,2}\/\d{2,4}\b/;
const moneyPattern = /(?:-\s*\$?\s*|\$\s*|\()?\d[\d,]*\.\d{2}\)?-?/g;
export function dateISO(value) {
  const raw = String(value ?? '').trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
  const m = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2}|\d{4})$/);
  if (!m) return '';
  const year = m[3].length === 2 ? `20${m[3]}` : m[3];
  const result = `${year}-${m[1].padStart(2, '0')}-${m[2].padStart(2, '0')}`;
  const d = new Date(`${result}T12:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === result ? result : '';
}
export const layouts = [
  { id: 'ace', vendor: 'Ace Endico', pattern: /ace\s*endico/i, amount: [.23, .39], balance: [.67, .83], credit: [.54, .68] },
  { id: 'aif', vendor: 'Adventure in Food', pattern: /adventure\s*(?:in)?\s*food|billfire/i },
  { id: 'antonucci', vendor: 'Antonucci Foods', pattern: /antonucci/i, amount: [.38, .54], balance: [.63, .79] },
  { id: 'argyle', vendor: 'Argyle Cheese Farmers', pattern: /argyle/i, amount: [.45, .59], balance: [.59, .75] },
  { id: 'bakemark', vendor: 'BakeMark', pattern: /bake\s*mark/i, amount: [.62, .80], balance: [.80, .96] },
  { id: 'rinella', vendor: 'A.J. Rinella', pattern: /rinella/i, amount: [.38, .51], balance: [.74, .86] },
];
const values = text => [...text.matchAll(moneyPattern)].map(m => cents(m[0])).filter(n => n !== null);
function positionedMoney(line) {
  return (line.words ?? []).flatMap(word => {
    return [...word.text.matchAll(moneyPattern)].map(m => ({ value: cents(m[0]), x: word.x + ((word.width ?? .03) * (m.index + m[0].length / 2) / Math.max(word.text.length, 1)) }));
  }).filter(item => item.value !== null);
}
function column(line, range) {
  if (!range) return null;
  return positionedMoney(line).find(v => v.x >= range[0] && v.x < range[1])?.value ?? null;
}
function cleanReference(text) {
  return text.replace(/^Invoice\s*#?\s*/i, '').trim();
}
export function parseStatement(pages, filename = 'statement.pdf') {
  const full = pages.map(p => p.lines.map(l => l.text).join('\n')).join('\n');
  const layout = layouts.find(l => l.pattern.test(full + ' ' + filename)) ?? { id: 'generic', vendor: 'Unidentified vendor' };
  const rows = [];
  const warnings = [];
  let statementDate = '';
  let declaredTotal = null;
  let openingBalance = null;
  for (const page of pages) {
    const lines = page.lines;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const text = line.text.trim();
      if (!statementDate && /statement\s*date|as of|\bdate\s*:/i.test(text)) statementDate = dateISO(text.match(datePattern)?.[0]);
      if (!statementDate && /\bdate\b/i.test(text) && line.y < .4) statementDate = dateISO(text.match(datePattern)?.[0]);
      if (/total\s*(?:amount\s*)?due|grand\s*total|invoice\s*total|^total\s*\$?/i.test(text) && !/subtotal|past due total|total balance/i.test(text)) {
        const found = values(text);
        if (found.length) declaredTotal = found.at(-1);
        else if (!/CONT/i.test(text)) {
          const next = lines.slice(i + 1, i + 3).find(l => values(l.text).length && !/\b\d{1,2}\/\d{1,2}\//.test(l.text));
          if (next) declaredTotal = values(next.text).at(-1);
        }
      }
      if (/balance\s*forward|opening\s*balance|brought\s*forward/i.test(text)) {
        const found = values(text);
        if (found.length) {
          openingBalance = found.at(-1);
          rows.push({ id: uid(), type: 'opening', invoiceNumber: '', date: dateISO(text.match(datePattern)?.[0]), amount: openingBalance, balance: openingBalance, page: page.page, source: text, confidence: line.confidence ?? 99 });
        }
        continue;
      }
      const dates = text.match(new RegExp(datePattern.source, 'g')) ?? [];
      const amounts = values(text);
      if (!amounts.length) continue;
      let invoiceNumber = '', type = 'invoice', amount = null, balance = null;
      if (layout.id === 'aif') {
        const match = text.match(/^([A-Za-z0-9][A-Za-z0-9-]{2,})\s+(?:\d{1,2}\/\d{1,2}\/\d{2,4}|-)\s+/);
        if (!match) continue;
        invoiceNumber = match[1]; amount = amounts.at(-1); balance = amount;
        if (amount < 0) type = 'credit';
      } else if (layout.id === 'antonucci') {
        const match = text.match(/^([A-Za-z0-9-]+)\s+(\d{1,2}\/\d{1,2}\/\d{2,4})\s+(IV|CM|PY)\b/i);
        if (!match) continue;
        invoiceNumber = match[1]; type = { IV: 'invoice', CM: 'credit', PY: 'payment' }[match[3].toUpperCase()];
        amount = column(line, layout.amount) ?? amounts[0]; balance = column(line, layout.balance);
        if (balance === null && !line.words?.length && amounts.length > 1) balance = amounts[1];
      } else if (layout.id === 'argyle') {
        if (!dates.length || !/^\d{1,2}\//.test(text)) continue;
        const match = text.match(/Invoice\s*#\s*([A-Za-z0-9-]+)/i);
        if (match) invoiceNumber = match[1];
        else if (/\bpayment\b/i.test(text)) type = 'payment';
        else continue;
        amount = column(line, layout.amount) ?? amounts[0];
        // The balance column here is the running account balance, not an invoice balance.
      } else if (['ace', 'bakemark', 'rinella'].includes(layout.id)) {
        if (!dates.length || !/^\d{1,2}\//.test(text)) continue;
        const afterDate = text.slice(text.indexOf(dates[0]) + dates[0].length).trim();
        invoiceNumber = afterDate.match(/^([A-Za-z0-9][A-Za-z0-9-]{2,})\b/)?.[1] ?? '';
        if (!invoiceNumber || /^\d+[.,]\d{2}$/.test(invoiceNumber)) continue;
        amount = column(line, layout.amount);
        balance = column(line, layout.balance);
        if (layout.id === 'ace' && (/-0A$/i.test(invoiceNumber) || column(line, layout.credit) < 0)) {
          type = 'credit'; amount = column(line, layout.credit) ?? amounts[0]; balance = amount;
        } else if (amount === null) amount = amounts[0];
        if (layout.id === 'bakemark' && balance === null) balance = amounts.at(-1);
        if (layout.id === 'rinella' && balance === null) balance = amounts.length > 1 ? amounts[1] : amount;
      } else {
        // Conservative fallback: explicit Invoice reference or dated invoice-table row only.
        const explicit = text.match(/\binvoice\s*#?\s*([A-Za-z0-9-]{2,})/i);
        const dated = text.match(/^\d{1,2}\/\d{1,2}\/\d{2,4}\s+([A-Za-z0-9][A-Za-z0-9-]{2,})\s/);
        if (!explicit && !dated) continue;
        invoiceNumber = cleanReference(explicit?.[1] ?? dated[1]);
        amount = amounts[0]; balance = null;
      }
      if (amount == null) continue;
      rows.push({ id: uid(), invoiceNumber, type, date: layout.id === 'aif' ? '' : dateISO(dates[0]), dueDate: layout.id === 'aif' ? dateISO(dates[0]) : (layout.id === 'bakemark' ? dateISO(dates[1]) : ''), amount, balance, page: page.page, source: text, confidence: line.confidence ?? 99 });
    }
  }
  if (!rows.length) warnings.push('No transaction rows were identified. Review the PDF and add rows manually.');
  if (layout.id === 'generic') warnings.push('Unrecognized layout. Vendor name, row completeness and amounts require review.');
  if (pages.some(p => p.ocr)) warnings.push('Scanned PDF: verify invoice numbers and amounts against the original.');
  if (!statementDate) warnings.push('Statement date was not identified. Enter the date printed on the statement.');
  return { id: uid(), filename, vendor: layout.vendor, layout: layout.id, statementDate, declaredTotal, openingBalance, rows, warnings, pageCount: pages.length, ocr: pages.some(p => p.ocr), confirmed: false, demo: false, notes: '', assignee: '', createdAt: new Date().toISOString() };
}
export function totals(statement) {
  // BakeMark is an open-item statement: its total is remaining balances, not original charges.
  const sum = statement.rows.reduce((result, row) => result + (statement.layout === 'bakemark' && row.type === 'invoice' ? (row.balance ?? row.amount ?? 0) : (row.amount ?? 0)), 0);
  const difference = statement.declaredTotal == null ? null : sum - statement.declaredTotal;
  return { sum, difference, agrees: difference === 0 };
}
export function groupInvoices(statement) {
  const groups = new Map();
  const standalone = [];
  for (const row of statement.rows) {
    if (row.type === 'opening' || (!row.invoiceNumber && row.type === 'payment')) {
      standalone.push({ ...row, activity: [row], originalAmount: row.type === 'opening' ? row.amount : null, outstanding: row.amount, kind: row.type }); continue;
    }
    let key = invoiceKey(row.invoiceNumber);
    if (statement.layout === 'ace' && row.type === 'credit' && /-0A$/i.test(key)) key = key.replace(/-0A$/, '-00');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  const output = [...groups.entries()].map(([key, activity]) => {
    const invoices = activity.filter(r => r.type === 'invoice');
    const lastBalance = [...activity].reverse().find(r => r.balance != null && (statement.layout !== 'ace' || r.type === 'invoice'));
    const isInvoice = invoices.length > 0;
    return {
      id: invoices[0]?.id ?? activity[0].id, invoiceNumber: invoices[0]?.invoiceNumber ?? activity[0].invoiceNumber,
      kind: isInvoice ? 'invoice' : activity[0].type, activity, page: activity[0].page,
      originalAmount: isInvoice ? invoices.reduce((s, r) => s + r.amount, 0) : activity.reduce((s, r) => s + r.amount, 0),
      outstanding: lastBalance?.balance ?? (statement.layout === 'argyle' || statement.layout === 'generic' ? null : activity.reduce((s, r) => s + r.amount, 0)),
      date: invoices[0]?.date ?? activity[0].date, confidence: Math.min(...activity.map(r => r.confidence ?? 99)),
      duplicate: invoices.length > 1, key,
    };
  });
  return [...output, ...standalone];
}
export const statuses = {
  matched: { label: 'Matched', tone: 'green' }, missing: { label: 'Not found', tone: 'red' },
  amount: { label: 'Amount differs', tone: 'amber' }, balance: { label: 'Balance differs', tone: 'amber' },
  scheduled: { label: 'Payment scheduled', tone: 'blue' }, paid: { label: 'Payment review', tone: 'amber' },
  ambiguous: { label: 'Multiple matches', tone: 'amber' }, extraction: { label: 'Check extraction', tone: 'amber' },
  unverified: { label: 'BILL unavailable', tone: 'gray' }, credit: { label: 'Credit review', tone: 'blue' },
  history: { label: 'History needed', tone: 'amber' }, presence: { label: 'Invoice found', tone: 'blue' },
};
export function reconcile(statement, provider, mappings = {}) {
  const vendor = vendorKey(mappings[statement.vendor] || statement.vendor);
  const records = provider.records ?? [];
  return groupInvoices(statement).map(row => {
    const result = (status, reason, candidates = []) => ({ ...row, status, reason, candidates, statementId: statement.id, vendor: statement.vendor, simulated: !!provider.simulated });
    if (row.kind === 'opening') return result('history', 'Carried-forward balance: older invoice detail is needed. It is not a new invoice.');
    if (row.kind === 'payment') return result('history', 'Account-level payment: invoice allocations are not supplied by this statement.');
    if (!statement.confirmed || row.confidence < 80 || row.duplicate) return result('extraction', row.duplicate ? 'More than one invoice charge uses this number. Check the source rows.' : 'Confirm the extracted invoice numbers and amounts before matching.');
    if (!provider.loaded) return result('unverified', 'No BILL records are connected or imported. This does not mean the invoice is missing.');
    const candidates = records.filter(r => vendorKey(r.vendor) === vendor && invoiceKey(r.invoiceNumber) === invoiceKey(row.invoiceNumber) && (r.kind ?? 'invoice') === row.kind);
    if (candidates.length > 1) return result('ambiguous', 'Multiple BILL records have this vendor and reference. Review candidates.', candidates);
    if (!candidates.length) return result('missing', provider.simulated ? 'No match in the simulated BILL dataset.' : 'No match in the imported BILL records. Verify export coverage before treating this as missing.');
    const bill = candidates[0];
    if (bill.currency && bill.currency !== 'USD') return result('amount', 'Currency differs from this USD statement. Review currency before comparing amounts.', candidates);
    if (row.kind === 'credit') return result('credit', 'Credit reference found. Verify the credited amount and where it was applied.', candidates);
    if (row.originalAmount !== bill.amount) return result('amount', `Statement original amount ${money(row.originalAmount)}; BILL original amount ${money(bill.amount)}.`, candidates);
    const outstanding = bill.amount - (bill.creditAmount ?? 0) - (bill.clearedPaymentAmount ?? 0);
    if (bill.scheduledAmount > 0) return result('scheduled', `${money(bill.scheduledAmount)} is scheduled, not confirmed settled. Review vendor receipt and statement timing.`, candidates);
    if (row.outstanding == null) return result('presence', 'Invoice number and original amount agree. This statement does not establish an invoice-level outstanding balance.', candidates);
    if (row.outstanding !== outstanding) {
      const afterStatement = bill.paymentDate && statement.statementDate && bill.paymentDate > statement.statementDate;
      return result(outstanding === 0 || afterStatement ? 'paid' : 'balance', afterStatement ? `Payment dated ${bill.paymentDate} is after the statement date. Review timing.` : `Statement balance ${money(row.outstanding)}; BILL balance after cleared payments and credits ${money(outstanding)}.`, candidates);
    }
    if (!provider.simulated && provider.asOf && statement.statementDate && provider.asOf !== statement.statementDate) return result('presence', 'Invoice and current balance agree; historical balance as of the statement date is not verified.', candidates);
    return result('matched', provider.simulated ? 'Invoice and balance agree with simulated BILL records.' : 'Invoice and balance agree with imported records. Confirm their date and coverage.', candidates);
  });
}
export function parseCSV(text) {
  const lines = []; let row = [], field = '', quoted = false;
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (c === '"') { if (quoted && text[i + 1] === '"') { field += '"'; i++; } else quoted = !quoted; }
    else if (c === ',' && !quoted) { row.push(field); field = ''; }
    else if ((c === '\n' || c === '\r') && !quoted) { if (c === '\r' && text[i + 1] === '\n') i++; row.push(field); if (row.some(v => v.trim())) lines.push(row); row = []; field = ''; }
    else field += c;
  }
  if (quoted) throw new Error('CSV has an unclosed quoted field.');
  row.push(field); if (row.some(v => v.trim())) lines.push(row);
  return lines;
}
export function importRecords(text) {
  const [header, ...rows] = parseCSV(text);
  if (!header) throw new Error('CSV is empty.');
  const names = header.map(h => h.toLowerCase().replace(/[^a-z0-9]/g, ''));
  const required = ['vendor', 'invoicenumber', 'amount'];
  if (!required.every(n => names.includes(n))) throw new Error('Required CSV headers: vendor, invoiceNumber, amount. Download the template for optional fields.');
  const get = (row, name) => row[names.indexOf(name.toLowerCase())] ?? '';
  return rows.map((row, i) => {
    const amount = cents(get(row, 'amount'));
    const vendor = get(row, 'vendor').trim(); const invoiceNumber = get(row, 'invoiceNumber').trim();
    if (!vendor || !invoiceNumber || amount == null) throw new Error(`Invalid vendor, invoice number or amount on CSV row ${i + 2}.`);
    const fieldMoney = name => { const value = get(row, name); const parsed = cents(value); if (value.trim() && parsed == null) throw new Error(`Invalid ${name} on CSV row ${i + 2}.`); return parsed ?? 0; };
    return { id: get(row, 'id') || `csv-${i}`, vendor, invoiceNumber, amount, kind: get(row, 'kind') || 'invoice', currency: get(row, 'currency') || 'USD', clearedPaymentAmount: fieldMoney('clearedPaymentAmount'), scheduledAmount: fieldMoney('scheduledAmount'), creditAmount: fieldMoney('creditAmount'), paymentDate: dateISO(get(row, 'paymentDate')), status: get(row, 'status') };
  });
}
export function csvCell(value) {
  let str = String(value ?? '');
  if (/^[\s]*[=+@-]/.test(str) && !/^-\d+(?:\.\d+)?$/.test(str)) str = "'" + str;
  return `"${str.replace(/"/g, '""')}"`;
}
export const toCSV = rows => rows.map(row => row.map(csvCell).join(',')).join('\r\n');
