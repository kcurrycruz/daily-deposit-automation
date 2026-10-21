import {isAdventureInFoodVendor} from './vendor-identity.mjs';
const reference=value=>String(value??'').trim().toUpperCase().replace(/\s+/g,'');
const base=value=>reference(value).match(/^(\d+)[A-Z]?$/)?.[1]||null;

// Deliberately not fuzzy matching: preserve every digit, including leading zeros.
// Exactly one optional trailing letter is permitted for this resolved vendor only.
export function adventureReferenceKeys(vendor,value,kind='invoice'){
  const digits=base(value);
  return kind==='invoice'&&isAdventureInFoodVendor(vendor)&&digits
    ? [digits,...Array.from('ABCDEFGHIJKLMNOPQRSTUVWXYZ',letter=>digits+letter)] : [];
}
export function adventureAmountDiscrepancy(row){
  const bill=row?.candidates?.length===1?row.candidates[0]:null;
  return !!(row?.referenceRule==='adventure-trailing-letter-v1'&&row.status==='amount'&&row.matchMethod==='reference'&&!row.preview&&!row.simulated&&!row.duplicate&&
    (row.kind??'invoice')==='invoice'&&bill&&(bill.kind??'invoice')==='invoice'&&!bill.sourceIssues&&(!bill.currency||bill.currency==='USD')&&
    isAdventureInFoodVendor(bill.vendor)&&base(row.invoiceNumber)&&base(row.invoiceNumber)===base(bill.invoiceNumber)&&
    Number.isSafeInteger(row.originalAmount)&&Number.isSafeInteger(bill.amount)&&row.originalAmount!==bill.amount);
}
