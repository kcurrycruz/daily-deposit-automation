// Requests travel only through the Streamlit SDK. No credentials in the frame.
export const LIMITS=Object.freeze({file:20*1024*1024,chunk:256*1024,envelope:1024*1024,records:100000,batch:500,pdfs:20});
export function createSharedClient({send,subscribe,timeoutMs=30000}) {
  const queue=[],identities=new Map();let active=null,disposed=false;
  const fail=(code,message,item)=>Object.assign(new Error(message),{code,retry:()=>request(item.action,item.payload,{requestId:item.id})});
  function advance(){
    if(active||disposed||!queue.length)return;
    active=queue.shift();const item=active;
    item.timer=setTimeout(()=>{if(active!==item)return;active=null;item.reject(fail('timeout','No save acknowledgement. Retry this operation before editing further.',item));advance();},timeoutMs);
    try{send({version:1,request_id:item.id,action:item.action,payload:item.payload});}
    catch{clearTimeout(item.timer);active=null;item.reject(fail('unavailable','Shared storage is unavailable. Retry this operation.',item));advance();}
  }
  const unsubscribe=subscribe(reply=>{
    if(!active||reply?.version!==1||reply.request_id!==active.id||typeof reply.ok!=='boolean')return;
    const item=active;clearTimeout(item.timer);active=null;
    if(reply.ok)item.resolve(reply.data);
    else item.reject(fail(reply.error?.code||'unavailable',reply.error?.message||'Not saved. Retry.',item));
    advance();
  });
  function request(action,payload,{requestId=crypto.randomUUID(),signal}={}){
    if(disposed)return Promise.reject(new Error('AP is locked. Unlock again.'));
    let snapshot,identity;
    try{snapshot=JSON.parse(JSON.stringify(payload));identity=JSON.stringify({action,payload:snapshot});
      if(new TextEncoder().encode(identity).length>LIMITS.envelope-256)throw new Error('Request exceeds the size limit.');
      if(identities.has(requestId)&&identities.get(requestId)!==identity)throw new Error('Request id has a different payload.');
    }catch(error){return Promise.reject(error);}
    identities.set(requestId,identity);
    return new Promise((resolve,reject)=>{
      const item={id:requestId,action,payload:snapshot,resolve,reject};
      if(signal?.aborted){reject(new Error('Request cancelled.'));return;}
      // Disposing the entire access session is the cancellation boundary. A
      // sent write may already have committed; retry keeps its original ID.
      queue.push(item);advance();
    });
  }
  return {request,dispose(){disposed=true;unsubscribe?.();if(active){clearTimeout(active.timer);active.reject(new Error('AP is locked.'));active=null;}for(const item of queue.splice(0))item.reject(new Error('AP is locked.'));identities.clear();}};
}
