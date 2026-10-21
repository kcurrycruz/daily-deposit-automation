import test from 'node:test';
import assert from 'node:assert/strict';
const module=await import('../app/ap_statements/frontend/reference-review.mjs').catch(()=>null);
const row=()=>({invoiceNumber:'271712',originalAmount:129981,status:'possible',matchMethod:'amount',candidates:[{vendor:'Adventure in Food',invoiceNumber:'271712X',amount:129981,currency:'USD'}]});
test('reference confirmation preserves both references and records an explicit review, not a new automatic match',()=>{
  assert.ok(module,'Reference difference review must exist');const original=row(),before=structuredClone(original);
  const review=module.confirmReferenceReview({confirmed:true},original,{note:'Keep my note'});
  assert.equal(review.decision,'Reviewed — no action needed');assert.match(review.note,/271712X/);assert.match(review.note,/271712\b/);assert.match(review.note,/Keep my note/);assert.deepEqual(original,before);
});
test('amount difference remains an investigation even when the user confirms the reference',()=>{
  assert.ok(module);const r=row();r.candidates[0].amount=129000;
  const review=module.confirmReferenceReview({confirmed:true},r,{});assert.equal(review.decision,'Investigate amount difference');
  assert.match(module.referenceReviewHTML({confirmed:true},r),/Amount difference/);
});
test('preliminary ambiguous foreign-currency or unsafe evidence cannot be confirmed through the shortcut',()=>{
  assert.ok(module);
  for(const r of [{...row(),preview:true},{...row(),candidates:[...row().candidates,...row().candidates]},{...row(),status:'vendor'},{...row(),candidates:[{...row().candidates[0],sourceIssues:'Incomplete source'}]},{...row(),candidates:[{...row().candidates[0],currency:'CAD'}]}])assert.throws(()=>module.confirmReferenceReview({confirmed:true},r,{}),/review/i);
  assert.throws(()=>module.confirmReferenceReview({confirmed:false},row(),{}),/review/i);
  assert.doesNotMatch(module.referenceReviewHTML({confirmed:true},row(),true),/confirm-reference/);
});
test('confirming a reference does not erase a previously saved follow-up decision',()=>{
  assert.ok(module);const result=module.confirmReferenceReview({confirmed:true},row(),{decision:'Check payment timing',note:'Awaiting vendor'});
  assert.equal(result.decision,'Check payment timing');assert.match(result.note,/Awaiting vendor/);
});
