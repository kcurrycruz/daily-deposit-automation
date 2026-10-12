const attached = new WeakSet();
export function attachStreamlitBridge(sdk, height = 900, target = undefined) {
  if (attached.has(sdk)) return;
  sdk.setComponentReady();
  sdk.setFrameHeight(height);
  target?.addEventListener('hwfc:return-to-programs', () => {
    // The only component value is navigation; never forward event detail.
    sdk.setComponentValue({ action: 'return_to_programs', request_id: crypto.randomUUID() });
  });
  attached.add(sdk);
}
