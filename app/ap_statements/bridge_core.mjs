import {createSharedClient} from './frontend/shared-client.mjs';
const attached = new WeakSet();
export function attachStreamlitBridge(sdk, height = 900, target = undefined) {
  if (attached.has(sdk)) return;
  sdk.setComponentReady();
  sdk.setFrameHeight(height);
  target?.addEventListener('hwfc:return-to-programs', () => {
    // The only component value is navigation; never forward event detail.
    sdk.setComponentValue({ action: 'return_to_programs', request_id: crypto.randomUUID() });
  });
  if (target && sdk.events) {
    const listeners=new Set();
    const client=createSharedClient({send:value=>sdk.setComponentValue(value),subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn);}});
    target.hwfcSharedClient=client;
    sdk.events.addEventListener(sdk.RENDER_EVENT,event=>{
      const args=event.detail?.args||{};
      for(const listener of listeners)listener(args.shared_reply);
    });
    target.dispatchEvent(new Event('hwfc:shared-ready'));
    target.addEventListener('pagehide',()=>client.dispose(),{once:true});
  }
  attached.add(sdk);
}
