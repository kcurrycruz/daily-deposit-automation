// Status only: never grants ownership or changes the scan/review rules.
export function duplicateProgressPresentation(state={},now=Date.now()){
 const p=state.progress||{},phase=['reading','candidates','packaging','complete'].includes(p.phase)?p.phase:'unknown';
 const last=Number.isFinite(state.lastAdvanceAt)?state.lastAdvanceAt:now;
 const elapsedSeconds=Math.floor(Math.max(0,now-last)/1000);
 const diagnostics={phase,checkpoint:Number.isSafeInteger(p.checkpoint)&&p.checkpoint>=0?p.checkpoint:null,elapsedSeconds};
 const result=(kind,title,message,busy=false)=>({kind,title,message,busy,diagnostics});
 if(state.error)return result('paused','Duplicate checks paused',`The last request could not continue. Use ${state.error.code==='duplicate_conflict'?'Refresh shared review':'Retry same operation'} to resume. Your saved BILL data is unchanged.`);
 if(['failed','restart_required','superseded'].includes(state.phase)||['failed','restart_required','superseded'].includes(p.state))return result('paused','Duplicate checks are not complete','Use the offered recovery action to check the saved BILL data again.');
 // A published scan's timestamp is immutable. Rebuilding its local review
 // projection is separate work and must not age into a stalled-scan warning.
 if(p.state==='ready')return p.projectionReady?
  result('ready','Duplicate checks ready','The complete pattern check is available for review.'):
  result('preparing','Preparing shared review history','The scan is complete. Loading its saved evidence and shared review history.',true);
 if(p.canStep===false&&p.state!=='ready')return result('waiting','Waiting for the active scan','Another session owns this scan. We are checking its status; your statements remain available.');
 if(elapsedSeconds>=60)return result('interrupted','No recent scan progress','No progress has been reported for at least a minute. Refresh shared review to check the latest status. Your saved BILL data is unchanged.');
 const title=p.state==='ready'?'Preparing shared review history':({reading:'Reading your saved bills',candidates:'Checking invoice patterns',packaging:'Packaging duplicate results'})[phase]||'Checking your saved bills';
 return result('active',title,'You can continue reviewing statements while this runs.',true);
}
