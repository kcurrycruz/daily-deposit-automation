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
