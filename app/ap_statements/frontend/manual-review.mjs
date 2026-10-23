const decisions=new Set(['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed']);
const identity=(doc,row)=>({vendor:row.vendor??doc?.vendor,reference:row.invoiceNumber??'',amount:row.originalAmount,kind:row.kind??'invoice'});
export function createManualCheck(doc,row,{initials,decision,note}={},prior={}){
 const normalized=String(initials??'').trim().toUpperCase();
 if(!/^[A-Z]{1,10}$/.test(normalized))throw Error('Manual-check initials must contain one to ten letters.');
 if(!decisions.has(decision))throw Error('Choose a valid review decision.');
 const proof=identity(doc,row);
 if(typeof proof.vendor!=='string'||!proof.vendor.trim()||typeof proof.reference!=='string'||!Number.isSafeInteger(proof.amount)||!['invoice','credit','payment','opening'].includes(proof.kind))throw Error('Open a valid statement item before checking it manually.');
 // No client timestamp: the label appears only after server acknowledgement.
 return {decision,note:String(note??prior.note??''),manualCheck:{...proof,initials:normalized}};
}
export function manualCheckFor(row,resolution){
 const proof=resolution?.manualCheck;
 if(!proof||!decisions.has(resolution.decision)||!Number.isFinite(Date.parse(resolution.at))||!/^[A-Z]{1,10}$/.test(proof.initials||''))return null;
 const expected=identity(null,row);
 return Object.entries(expected).every(([key,value])=>proof[key]===value)?proof:null;
}
