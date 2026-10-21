const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function statementDay(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const date=new Date(value+'T00:00:00Z');
  return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value?value:null;
}
export function sortStatements(items,direction='desc'){
  return [...items].sort((a,b)=>{
    const left=statementDay(a.statementDate),right=statementDay(b.statementDate);
    if(!left&&right)return 1;
    if(left&&!right)return -1;
    if(left&&right&&left!==right)return direction==='asc'?left.localeCompare(right):right.localeCompare(left);
    const completed=(Date.parse(b.completedAt)||0)-(Date.parse(a.completedAt)||0);
    return completed||String(b.id||'').localeCompare(String(a.id||''));
  });
}
export function statementDateHeader(direction='desc',list='history'){
  const ascending=direction==='asc';
  return `<th aria-sort="${ascending?'ascending':'descending'}"><button class="statement-date-sort" data-action="statement-date-sort" data-list="${esc(list)}" aria-label="Statement Date: ${ascending?'oldest':'newest'} first. Sort ${ascending?'newest':'oldest'} first">Statement Date <span aria-hidden="true">${ascending?'↑':'↓'}</span></button></th>`;
}
// Work progress, not invoice presence or payment settlement. A follow-up decision
// always overrides an automatic match; generic no-action is a resolved work item.
export function reviewProgress(rows,resolutions={},confirmed=false){
  if(!confirmed||!Array.isArray(rows)||!rows.length||rows.some(row=>!row?.id||typeof row.status!=='string'))return null;
  return {resolved:rows.filter(row=>{
    const decision=resolutions?.[row.id]?.decision;
    return decision?decision==='Reviewed — no action needed':!row.preview&&!row.simulated&&['matched','presence'].includes(row.status);
  }).length,total:rows.length};
}
function validProgress(progress){
  return progress&&Number.isSafeInteger(progress.resolved)&&Number.isSafeInteger(progress.total)&&progress.total>0&&progress.resolved>=0&&progress.resolved<=progress.total;
}
export function progressHTML(progress){
  return `<small class="statement-progress">${validProgress(progress)?`${progress.resolved} of ${progress.total} items resolved`:'Progress unavailable'}</small>`;
}
export function reviewStatusHTML(status,progress){
  const done=['reconciled','reviewed'].includes(status),followUp=status==='follow_up';
  const tone=done?'green':followUp&&validProgress(progress)&&progress.resolved*2<progress.total?'red':'amber';
  const label=({reconciled:'Completed',reviewed:'Reviewed',follow_up:'Follow-up'})[status]||status;
  return `<span class="badge ${tone}"${done?' title="Review completed; payment settlement is not verified."':''}><span class="dot"></span>${esc(label)}</span>${status==='reviewed'?'<small class="statement-progress">Comparison limits remain</small>':''}${progressHTML(progress)}`;
}
