import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app/ap_statements/frontend/app.mjs',import.meta.url),'utf8');
test('save acknowledgements re-enable controls disabled during a shared write',()=>{
  const button={disabled:true};const context={saveState:'saving',sharedError:null,retryOperation:null,shared:{state:{ready:true,details:new Map()}},state:{selected:null},overlay:{querySelectorAll:()=>[]},document:{querySelector:()=>null,querySelectorAll:()=>[button]}};
  vm.runInNewContext(source.slice(source.indexOf('function sharedStatus('),source.indexOf('function receiveShared(')),context);
  context.sharedStatus('saved');assert.equal(button.disabled,false);context.sharedStatus('saving');assert.equal(button.disabled,true);
});
test('shared UI decoration does not duplicate navigation and save status on errors',()=>{
  let navAdds=0,statusAdds=0;const nav={querySelector:()=>navAdds?{}:null,insertAdjacentHTML(){navAdds++;}},actions={insertAdjacentHTML(){statusAdds++;}};
  const context={saveState:'saved',sharedError:null,shared:{state:{ready:true}},state:{view:'statements',statements:[]},icon:()=>'',esc:String,
    document:{querySelector:selector=>selector==='.nav'?nav:selector==='.top-actions'?actions:selector==='#shared-save-status'&&statusAdds?{}:null,querySelectorAll:()=>[]}};
  vm.runInNewContext(source.slice(source.indexOf('function decorateSharedUi('),source.indexOf('function historyPanel(')),context);
  context.decorateSharedUi();context.decorateSharedUi();assert.equal(navAdds,1);assert.equal(statusAdds,1);
});
