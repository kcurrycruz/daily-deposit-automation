import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
const bridgeURL = new URL('../app/ap_statements/bridge_core.mjs', import.meta.url);
async function bridge() {
  assert.ok(existsSync(bridgeURL), 'Streamlit bridge must be packaged');
  return (await import(bridgeURL)).attachStreamlitBridge;
}
test('announces_ready_and_height_once', async () => {
  const attach = await bridge(); const calls = [];
  const sdk = { setComponentReady: () => calls.push('ready'), setFrameHeight: height => calls.push(height) };
  attach(sdk); attach(sdk);
  assert.deepEqual(calls, ['ready', 900], 'duplicate mounts must not reset or notify again');
});
test('never_sends_component_values', async () => {
  const attach = await bridge(); let values = 0;
  const sdk = { setComponentReady() {}, setFrameHeight() {}, setComponentValue() { values++; } };
  attach(sdk); attach(sdk); assert.equal(values, 0);
});

test('only_explicit_exit_event_sends_navigation_without_event_detail', async () => {
  const attach = await bridge(), target = new EventTarget(), values = [];
  const sdk = { setComponentReady() {}, setFrameHeight() {}, setComponentValue(value) { values.push(value); } };
  attach(sdk, 900, target); attach(sdk, 900, target);
  target.dispatchEvent(new Event('arbitrary-event'));
  assert.deepEqual(values, []);
  target.dispatchEvent(new CustomEvent('hwfc:return-to-programs', { detail: { invoices: ['private'], pdfBytes: 'private' } }));
  assert.equal(values.length, 1);
  assert.deepEqual(Object.keys(values[0]).sort(), ['action', 'request_id']);
  assert.equal(values[0].action, 'return_to_programs');
  assert.match(values[0].request_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  target.dispatchEvent(new Event('hwfc:return-to-programs'));
  assert.notEqual(values[0].request_id, values[1].request_id);
});
