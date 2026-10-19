const key=value=>String(value??'').trim().toLowerCase().replace(/\s+/g,' ');
export function providerVendors(provider,statementId){
  const scope=provider.scopes?.[statementId];
  return scope?.directoryComplete?scope.vendorDirectory:(provider.vendorDirectory||provider.records||[]);
}
// Preserve meaningful symbols (A&B is not AB) and branch/location words.
function nameStem(value){
  let result=key(value).replace(/[.,]/g,'').replace(/\s+/g,' ');
  const suffix=/\s+(?:incorporated|inc|llc|ltd|limited|corporation|corp|company|co)$/;
  while(suffix.test(result))result=result.replace(suffix,'').trim();
  return result.replace(/\s+&$/,'').trim();
}
export function resolveStatementVendor(name,records=[],mappings={}){
  const names=[...new Map(records.filter(r=>key(r.vendor)).map(r=>[key(r.vendor),r.vendor])).values()];
  const choices=names.sort((a,b)=>a.localeCompare(b));
  const remembered=Object.hasOwn(mappings,name),wanted=key(remembered?mappings[name]:name);
  const exact=names.find(n=>key(n)===wanted);
  if(exact)return {status:remembered?'remembered':'exact',vendor:exact,candidates:[],choices};
  const unknown=!wanted||['unidentified vendor','unknown','unidentified'].includes(wanted);
  const stem=nameStem(name),same=unknown||remembered?[]:names.filter(n=>nameStem(n)===stem);
  if(same.length===1&&/[a-z]{4}/.test(stem))return {status:'automatic',vendor:same[0],candidates:[],choices};
  const tokens=new Set(stem.split(/\s+/).filter(t=>t.length>2));
  const scored=names.map(n=>({name:n,score:nameStem(n).split(/\s+/).filter(t=>tokens.has(t)).length}));
  const candidates=same.length?same:unknown?[]:scored.filter(n=>n.score>0).sort((a,b)=>b.score-a.score||a.name.localeCompare(b.name)).slice(0,5).map(n=>n.name);
  return {status:candidates.length?'confirm':'unknown',vendor:null,candidates,choices};
}
