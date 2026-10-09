const SESSION_KEY = 'hwfc-ap-statements-session-v1';
const VENDOR_KEY = 'hwfc-ap-statements-vendors-v1';
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const fields = (value, allowed) => {
  if (!object(value)) throw Error('Invalid metadata');
  const result = {};
  for (const key of allowed.split(' ')) {
    const item = value[key];
    if (item === undefined) continue;
    if (item !== null && !['string', 'boolean', 'number'].includes(typeof item)) throw Error('Invalid metadata field');
    if (typeof item === 'number' && !Number.isFinite(item)) throw Error('Invalid number');
    result[key] = item;
  }
  return result;
};
function metadata(value) {
  if (!object(value) || value.version !== 1 || !Array.isArray(value.statements) ||
      !object(value.provider) || !Array.isArray(value.provider.records) || !object(value.resolutions)) throw Error('Invalid session');
  const statements = value.statements.map(doc => {
    if (!object(doc) || !Array.isArray(doc.rows) || !Array.isArray(doc.warnings) ||
        typeof doc.id !== 'string' || typeof doc.vendor !== 'string' || typeof doc.filename !== 'string') throw Error('Invalid statement');
    const result = fields(doc, 'id vendor filename layout statementDate declaredTotal openingBalance confirmed demo pageCount ocr notes assignee createdAt fileSize fileModified rawText');
    result.rows = doc.rows.map(row => {
      if (!object(row) || typeof row.id !== 'string' || typeof row.invoiceNumber !== 'string') throw Error('Invalid row');
      return fields(row, 'id invoiceNumber type date dueDate amount balance page source confidence');
    });
    if (!doc.warnings.every(w => typeof w === 'string')) throw Error('Invalid warnings');
    result.warnings = [...doc.warnings];
    return result;
  });
  const provider = fields(value.provider, 'loaded simulated label refreshedAt asOf');
  if (typeof provider.loaded !== 'boolean' || typeof provider.simulated !== 'boolean') throw Error('Invalid provider');
  provider.records = value.provider.records.map(row => {
    if (!object(row) || typeof row.vendor !== 'string' || typeof row.invoiceNumber !== 'string') throw Error('Invalid record');
    return fields(row, 'id vendor invoiceNumber amount kind currency clearedPaymentAmount scheduledAmount creditAmount paymentDate status');
  });
  const resolutions = Object.fromEntries(Object.entries(value.resolutions).map(([key, resolution]) =>
    [key, fields(resolution, 'note decision at')]));
  return { version: 1, statements, provider, resolutions };
}
function mappings(value) {
  if (!object(value) || !Object.values(value).every(v => typeof v === 'string')) throw Error('Invalid mappings');
  return Object.fromEntries(Object.entries(value));
}
export function loadSession(storage) {
  try {
    const raw = storage.getItem(SESSION_KEY);
    return { session: raw === null ? null : metadata(JSON.parse(raw)), error: null };
  } catch { return { session: null, error: 'Saved AP session could not be loaded. Browser storage may be blocked or corrupt. In-memory work still works; export your report before leaving.' }; }
}
export function saveSession(storage, session) {
  try { storage.setItem(SESSION_KEY, JSON.stringify(metadata(session))); return { ok: true, error: null }; }
  catch { return { ok: false, error: 'AP session was NOT saved. Check browser storage permissions or space; export your report before leaving. Your in-memory work remains available.' }; }
}
export function loadVendorMappings(storage) {
  try {
    const raw = storage.getItem(VENDOR_KEY);
    return { mappings: raw === null ? {} : mappings(JSON.parse(raw)), error: null };
  } catch { return { mappings: {}, error: 'Saved vendor mappings could not be loaded. Browser storage may be blocked or corrupt.' }; }
}
export function saveVendorMappings(storage, value) {
  try { storage.setItem(VENDOR_KEY, JSON.stringify(mappings(value))); return { ok: true, error: null }; }
  catch { return { ok: false, error: 'Vendor mapping was NOT saved to this browser. Check storage permissions or space; the in-memory mapping remains available. Export your report.' }; }
}
export function clearSession(storage) {
  try { storage.removeItem(SESSION_KEY); storage.removeItem(VENDOR_KEY); return { ok: true, error: null }; }
  catch { return { ok: false, error: 'Browser-local AP data could not be fully cleared. Check storage permissions or clear site data in browser settings. In-memory work has been retained.' }; }
}
