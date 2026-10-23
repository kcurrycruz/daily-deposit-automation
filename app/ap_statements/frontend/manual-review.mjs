const decisions=new Set(['Follow up with vendor','Request missing invoice','Check payment timing','Check credit application','Investigate amount difference','Reviewed — no action needed']);
const identity=(doc,row)=>({vendor:row.vendor??doc?.vendor,reference:row.invoiceNumber??'',amount:row.originalAmount,kind:row.kind??'invoice'});
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
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
export function rereviewChoiceHTML(vendor){
 return `<p>Re-review <strong>${esc(vendor)}</strong> starting from the <strong>latest revision</strong>, not an older historical copy. Previous reviews remain unchanged.</p><fieldset class="rereview-options"><legend>How would you like to review?</legend><label><input type="radio" name="rereview-mode" value="latest" checked><span><strong>Recheck with latest BILL data</strong><small>Keep statement corrections and notes. Compare again and clear superseded decisions.</small></span></label><label><input type="radio" name="rereview-mode" value="manual"><span><strong>Review manually</strong><small>Keep the saved comparison and decisions. Update items after checking them directly in BILL.</small></span></label></fieldset>`;
}
export function manualReviewBannerHTML(detail){
 return `<div class="notice blue manual-review-banner"><div><strong>Manual re-review · saved comparison retained</strong><p>Using ${esc(detail.importLabel||detail.importInfo?.metadata?.label||'the saved BILL export')} · ${esc(detail.ruleVersion||'saved rule version')}. Weekly BILL updates do not change these comparisons. Check items directly in BILL and record your decisions below.</p><p>Manual checks are self-reported; they do not verify imported invoice presence, payment settlement or credit application.</p><button class="button small" data-action="manual-recheck">Recheck with latest BILL data</button></div></div>`;
}
export function manualCheckHTML(row,resolution,readOnly=false){
 const proof=manualCheckFor(row,resolution);
 const saved=proof?`<p class="manual-check-saved">Checked manually in BILL · ${esc(proof.initials)} · ${esc(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',dateStyle:'medium',timeStyle:'short'}).format(new Date(resolution.at)))} (New York)</p>`:'';
 if(readOnly)return saved;
 return `<fieldset class="manual-check-controls"><legend>Manual BILL check</legend>${saved}<label><input type="checkbox" id="review-manual-check" ${proof?'checked':''}>I checked this item directly in BILL</label><label class="field">Manual-check initials<input id="review-manual-initials" maxlength="10" pattern="[A-Za-z]{1,10}" value="${esc(proof?.initials||'')}" placeholder="Required when checked" autocomplete="off"></label><small>Initials are self-reported. Save a review decision to record this check. The imported comparison remains unchanged.</small></fieldset>`;
}
export function manualExtractionHTML(doc){
 return `<section class="manual-extraction"><h3>Saved financial rows · read-only in manual mode</h3><p>Recheck with latest BILL data before correcting references, vendors, dates or amounts. Notes and review decisions remain editable.</p><button class="button" data-action="manual-recheck">Recheck with latest BILL data</button><div class="table-wrap"><table class="main-table"><thead><tr><th>Reference</th><th>Type</th><th>Original amount</th><th>Page</th></tr></thead><tbody>${doc.rows.map(row=>`<tr><td>${esc(row.invoiceNumber)}</td><td>${esc(row.type)}</td><td>${esc((row.amount/100).toLocaleString('en-US',{style:'currency',currency:'USD'}))}</td><td>${esc(row.page)}</td></tr>`).join('')}</tbody></table></div></section>`;
}
export function manualReviewReport(row,resolution){
 const proof=manualCheckFor(row,resolution);return proof?['Checked manually in BILL',proof.initials,resolution.at]:['','',''];
}
export function assertManualFinancialAction(doc,action){
 if(doc?.reviewMode==='manual'&&['save-extraction','confirm-extraction','add-row','delete-row','vendor-confirm','vendor-choose','confirm-reading','attach-original'].includes(action))throw Error('Recheck with latest BILL data before changing saved financial rows. Manual notes and decisions remain editable.');
}
