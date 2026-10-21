import {cents,invoiceKey} from './core.mjs';
// Preview-only evidence. No fuzzy references, amount-only hits, or OCR guesses.
export function findSourceLine(items,{reference,amount}){
  const wanted=invoiceKey(reference);if(!wanted||!Number.isSafeInteger(amount))return null;
  const groups=[];
  for(const item of items){if(!item.str?.trim()||!Array.isArray(item.transform))continue;const y=item.transform[5];let group=groups.find(line=>Math.abs(line.y-y)<2);if(!group){group={y,items:[]};groups.push(group);}group.items.push(item);}
  const hits=[];
  for(const group of groups){
    const words=group.items.sort((a,b)=>a.transform[4]-b.transform[4]);const text=words.map(item=>item.str.trim()).join(' ');
    const refs=text.toUpperCase().split(/\s+/).map(value=>value.replace(/^[#:]+|[:,;]+$/g,''));
    const values=[...text.matchAll(/\(?[+-]?\$?\d[\d,]*\.\d{2}\)?/g)].map(match=>cents(match[0]));
    if(!refs.includes(wanted)||!values.includes(amount))continue;
    // A shared baseline may contain separate invoice columns. Never pair a
    // reference with another region's amount; uncertain lines use the excerpt.
    const identifiers=text.replace(/\(?[+-]?\$?\d[\d,]*\.\d{2}\)?/g,' ').split(/\s+/).map(value=>value.replace(/^[#:]+|[:,;]+$/g,'')).filter(value=>/\d/.test(value));
    if(identifiers.length!==1||invoiceKey(identifiers[0])!==wanted)continue;
    const left=Math.min(...words.map(item=>item.transform[4])),right=Math.max(...words.map(item=>item.transform[4]+(item.width||0))),height=Math.max(...words.map(item=>item.height||Math.abs(item.transform[3])||10));
    hits.push({text,x:left,y:group.y,width:right-left,height});
  }
  return hits.length===1?hits[0]:null;
}
