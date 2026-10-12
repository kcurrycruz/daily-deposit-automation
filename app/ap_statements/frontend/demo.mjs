import { uid } from './core.mjs';
export function createDemo() {
  const definitions = [
    ['Northfield Produce', 'northfield-september.pdf', [['NP-2101', 34500, 'matched'], ['NP-2102', 18275, 'missing'], ['NP-2103', 42000, 'matched'], ['NP-2104', 9700, 'amount']]],
    ['Cedar Bakery Supply', 'cedar-september.pdf', [['CB-801', 61200, 'matched'], ['CB-802', 24500, 'scheduled'], ['CB-803', 17850, 'paid']]],
    ['Riverbend Dairy', 'riverbend-september.pdf', [['000491', 28760, 'matched'], ['000492', 53000, 'balance'], ['000493', 19800, 'matched']]],
  ];
  const records = [];
  const statements = definitions.map(([vendor, filename, entries]) => {
    const rows = entries.map(([invoiceNumber, amount, scenario], i) => {
      if (scenario !== 'missing') records.push({ id: uid(), vendor, invoiceNumber, amount: amount + (scenario === 'amount' ? 2500 : 0), currency: 'USD', kind: 'invoice', clearedPaymentAmount: scenario === 'paid' ? amount : 0, scheduledAmount: scenario === 'scheduled' ? amount : 0, creditAmount: scenario === 'balance' ? 8000 : 0, paymentDate: scenario === 'paid' ? '2026-10-03' : '', status: scenario === 'paid' ? 'PAID' : 'UNPAID' });
      return { id: uid(), invoiceNumber, type: 'invoice', date: `2026-09-${String(5 + i * 7).padStart(2, '0')}`, amount, balance: amount, page: 1, source: `${invoiceNumber} | ${amount / 100} | Fictional demonstration row`, confidence: 99 };
    });
    return { id: uid(), vendor, filename, layout: 'demo', statementDate: '2026-10-01', declaredTotal: rows.reduce((s, r) => s + r.amount, 0), rows, confirmed: true, demo: true, pageCount: 1, ocr: false, warnings: [], notes: '', assignee: '' };
  });
  return { statements, provider: { loaded: true, simulated: true, records, label: 'Simulated BILL records', asOf: '2026-10-01', refreshedAt: new Date().toISOString() } };
}
export function simulateRecords(statements) {
  const records = [];
  for (const statement of statements) {
    let index = 0;
    const seen = new Set();
    for (const row of statement.rows) {
      if (row.type !== 'invoice' || seen.has(row.invoiceNumber)) continue;
      seen.add(row.invoiceNumber); index++;
      if (index % 7 === 0) continue;
      records.push({ id: uid(), vendor: statement.vendor, invoiceNumber: row.invoiceNumber, amount: row.amount + (index % 9 === 0 ? 1000 : 0), currency: 'USD', kind: 'invoice', clearedPaymentAmount: index % 6 === 0 ? row.amount : 0, scheduledAmount: index % 5 === 0 ? Math.max(row.balance ?? row.amount, 0) : 0, creditAmount: row.balance != null && row.balance >= 0 && row.balance < row.amount ? row.amount - row.balance : 0 });
    }
  }
  return { loaded: true, simulated: true, records, label: 'Generated demonstration records', refreshedAt: new Date().toISOString(), asOf: '' };
}
