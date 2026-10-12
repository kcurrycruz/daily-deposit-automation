import test from 'node:test';
import assert from 'node:assert/strict';

test('sidebar_go_back_control_is_labeled_and_available', async () => {
  const { backButtonHtml } = await import('../app/ap_statements/frontend/navigation.mjs');
  const html = backButtonHtml();
  assert.match(html, /<button[^>]*data-action="back-to-programs"/);
  assert.match(html, /Go back to programs/);
  assert.match(html, /type="button"/);
});

test('navigation_requires_confirmation_and_dispatches_no_financial_payload', async () => {
  const { requestProgramHub } = await import('../app/ap_statements/frontend/navigation.mjs');
  const target = new EventTarget(), events = [];
  target.addEventListener('hwfc:return-to-programs', event => events.push(event));
  requestProgramHub(target, false);
  requestProgramHub(target);
  assert.equal(events.length, 0);
  requestProgramHub(target, true);
  assert.equal(events.length, 1);
  assert.equal(events[0].detail, undefined);
});
