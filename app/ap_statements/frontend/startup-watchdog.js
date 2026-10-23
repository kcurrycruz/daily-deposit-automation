// Classic script: still runs when the app or bridge module fails to load.
(() => {
 if(window.hwfcStartupWatchdog)return;
 let appReady=false,bridgeReady=false,timer;
 const dispose=()=>{clearTimeout(timer);timer=null;};
 const check=()=>{if(appReady&&bridgeReady)dispose();};
 window.hwfcStartupWatchdog={markAppReady(){appReady=true;check();},markBridgeReady(){bridgeReady=true;check();},dispose};
 timer=setTimeout(()=>{
  dispose();
  const app=document.querySelector('#app');
  // Only the loading skeleton is eligible; never cover a workspace or error.
  if(!app?.querySelector('.workspace-startup[aria-busy="true"]'))return;
  app.innerHTML='<main class="workspace-startup"><section class="startup-card" role="alert"><h1>Your AP workspace could not connect</h1><p>The application connection did not initialize. Your saved data has not changed. Check your connection, then reload to try again.</p><button id="ap-startup-reload" type="button" class="button primary">Reload application</button></section></main>';
  app.querySelector('#ap-startup-reload')?.addEventListener('click',()=>window.location.reload());
 },20000);
 window.addEventListener('pagehide',dispose,{once:true});
})();
