import test from 'node:test';
import assert from 'node:assert/strict';
import { createDemo } from '../app/ap_statements/frontend/demo.mjs';
import { loadSession, saveSession, clearSession, loadVendorMappings, saveVendorMappings } from '../app/ap_statements/frontend/session.mjs';

function storage() {
  const values = new Map();
  return { values, getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
}
const fixture = () => ({ version: 1, ...createDemo(), resolutions: { row: { note: 'Reviewed', decision: 'Follow up', at: '2026-10-09' } } });
test('metadata round trip preserves rows, notes, provider and reviews', () => {
  const s = storage(), data = fixture();
  data.statements[0].notes = 'Fictional note';
  assert.equal(saveSession(s, data).ok, true);
  assert.deepEqual(loadSession(s).session, data);
  assert.equal(s.values.has('hwfc-ap-statements-session-v1'), true);
  assert.equal(s.values.has('statement-desk-session'), false);
});
test('explicit allowlists omit PDF bytes, canvas, objects and URLs at every level', () => {
  const s = storage(), data = fixture();
  data.pdf = 'PDF_BYTES_SENTINEL';
  data.statements[0].pdf = 'PDF_BYTES_SENTINEL';
  data.statements[0].rows[0].canvas = 'PDF_BYTES_SENTINEL';
  data.provider.records[0].file = 'PDF_BYTES_SENTINEL';
  data.resolutions.row.original = 'PDF_BYTES_SENTINEL';
  saveSession(s, data);
  assert.equal([...s.values.values()].join('').includes('PDF_BYTES_SENTINEL'), false);
});
test('malformed JSON, wrong versions and malformed nested data are rejected safely', () => {
  const s = storage();
  for (const value of ['{', '{"version":2,"statements":[]}', '{"version":1,"statements":[null]}']) {
    s.setItem('hwfc-ap-statements-session-v1', value);
    assert.equal(loadSession(s).session, null);
    assert.ok(loadSession(s).error);
  }
});
test('denied reads, quota writes and failed deletes return actionable errors', () => {
  const denied = { getItem() { throw Error('denied'); }, setItem() { throw Error('quota'); }, removeItem() { throw Error('denied'); } };
  assert.ok(loadSession(denied).error);
  assert.ok(loadVendorMappings(denied).error);
  assert.equal(saveSession(denied, fixture()).ok, false);
  assert.match(saveSession(denied, fixture()).error, /export/i);
  assert.equal(saveVendorMappings(denied, { vendor: 'BILL name' }).ok, false);
  assert.equal(clearSession(denied).ok, false);
});
test('vendor mappings require strings and clearing removes both dedicated keys only', () => {
  const s = storage();
  s.setItem('daily-upload', 'untouched');
  saveSession(s, fixture());
  assert.equal(saveVendorMappings(s, { vendor: 'BILL vendor' }).ok, true);
  assert.deepEqual(loadVendorMappings(s).mappings, { vendor: 'BILL vendor' });
  s.setItem('hwfc-ap-statements-vendors-v1', '{"vendor":null}');
  assert.ok(loadVendorMappings(s).error);
  assert.equal(clearSession(s).ok, true);
  assert.equal(loadSession(s).session, null);
  assert.deepEqual(loadVendorMappings(s).mappings, {});
  assert.equal(s.getItem('daily-upload'), 'untouched');
});
