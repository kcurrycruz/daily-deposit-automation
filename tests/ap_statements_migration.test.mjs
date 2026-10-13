import test from 'node:test';
import assert from 'node:assert/strict';
import {legacyMigrationPreview,createSharedWorkspace} from '../app/ap_statements/frontend/shared-workspace.mjs';
const session=()=>({version:1,statements:[{id:'old-id',vendor:'Alpha',filename:'legacy.pdf',notes:'Keep prior work',rows:[],warnings:[],pageCount:1,confirmed:true},{id:'sample',demo:true,vendor:'Sample',filename:'demo.pdf'}],provider:{loaded:true,simulated:true,records:[{vendor:'Example'}]},resolutions:{}});
test('preview excludes samples and marks missing originals without sending requests',()=>{
  const value=legacyMigrationPreview(session(),{});assert.equal(value.statements.length,1);assert.equal(value.originalsAvailable,0);assert.equal(value.importMetadata,null);assert.equal(value.statements[0].doc.notes,'Keep prior work');assert.equal(value.statements[0].doc.confirmed,false);
});
test('migration only sends after confirmation, preserves legacy input on failure',async()=>{
  const requests=[];const client={dispose(){},async request(action,payload){requests.push(action);throw Error('offline');}};const workspace=createSharedWorkspace(client);const legacy=session(),before=JSON.stringify(legacy),preview=legacyMigrationPreview(legacy,{});
  await workspace.migrateLegacy(preview,false);assert.deepEqual(requests,[]);
  await assert.rejects(workspace.migrateLegacy(preview,true),/offline/);assert.equal(JSON.stringify(legacy),before);assert.deepEqual(requests,['migrate_legacy']);
});
