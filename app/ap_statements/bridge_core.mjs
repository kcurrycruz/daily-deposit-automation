const attached = new WeakSet();
export function attachStreamlitBridge(sdk, height = 900) {
  if (attached.has(sdk)) return;
  sdk.setComponentReady();
  sdk.setFrameHeight(height);
  attached.add(sdk);
}
