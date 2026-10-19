// Only compressed bytes travel over the bridge. CSV parsing remains on the server.
const SOURCE_LIMIT=256*1024*1024,PACKED_LIMIT=32*1024*1024,CHUNK=256*1024;
const abortError=()=>new DOMException('BILL update cancelled.','AbortError');
const copy=value=>JSON.parse(JSON.stringify(value));
export function prepareBillUpload(file,{onProgress=()=>{},signal,workerFactory}={}){
  if(signal?.aborted)return Promise.reject(abortError());
  if(!Number.isInteger(file?.size)||file.size<1||file.size>SOURCE_LIMIT)return Promise.reject(Error('Choose a CSV no larger than 256 MiB.'));
  return new Promise((resolve,reject)=>{
    let worker,finished=false;const id=crypto.randomUUID();
    const finish=(error,result)=>{if(finished)return;finished=true;signal?.removeEventListener('abort',abort);if(worker){worker.onmessage=null;worker.onerror=null;worker.terminate();}error?reject(error):resolve(result);};
    const abort=()=>finish(abortError());signal?.addEventListener('abort',abort,{once:true});
    try{
      if(!workerFactory&&typeof Worker!=='function')throw Error('This browser needs Web Worker and streaming compression support for BILL exports.');
      worker=workerFactory?workerFactory():new Worker(new URL('./bill-upload-worker.mjs',import.meta.url),{type:'module'});
      worker.onmessage=({data})=>{
        if(finished||data?.id!==id)return;
        if(data.type==='progress'){const p=data.progress;if(Number.isInteger(p?.processed)&&p.processed>=0&&p.processed<=file.size)onProgress(p);return;}
        if(data.type==='error'){finish(Error(data.message||'BILL export preparation failed.'));return;}
        if(data.type!=='result')return;
        if(!(data.blob instanceof Blob)||data.blob.size<1||data.blob.size>PACKED_LIMIT||data.originalBytes!==file.size){finish(Error('The prepared BILL export could not be verified.'));return;}
        finish(null,{blob:data.blob,originalBytes:data.originalBytes});
      };
      worker.onerror=()=>finish(Error('The BILL preparation worker could not finish. Retry with a browser supporting streaming compression.'));
      worker.postMessage({type:'compress',id,file});
      if(signal?.aborted)abort();
    }catch(error){finish(error);}
  });
}
function base64(bytes){let value='';for(const byte of bytes)value+=String.fromCharCode(byte);return btoa(value);}

export function importBillSnapshot(client,file,{asOf='',onProgress=()=>{},signal,confirmRestore=async()=>false,confirmRestart=async()=>false,workerFactory}={}){
  const steps=new Map();let packed=null,job=null;
  function check(){if(signal?.aborted)throw abortError();}
  async function request(key,action,payload){
    check();let step=steps.get(key);
    if(!step){step={id:crypto.randomUUID(),action};steps.set(key,step);}
    if(step.action!==action)throw Error('The BILL retry operation changed. Select the file again.');
    if(Object.hasOwn(step,'reply'))return copy(step.reply);
    const reply=await client.request(action,payload,{requestId:step.id,signal});step.reply=copy(reply);
    if(action==='bill_upload_begin'&&typeof reply?.job_id==='string')job=copy(reply);
    check();return reply;
  }
  async function cancel(){
    if(job?.job_id)await client.request('bill_cancel',{job_id:job.job_id},{requestId:crypto.randomUUID()}).catch(()=>{});
    return {cancelled:true};
  }
  async function execute(){
    try{
      check();
      if(!packed){onProgress({stage:'preparing',fraction:0});packed=await prepareBillUpload(file,{signal,workerFactory,onProgress:p=>onProgress({stage:'preparing',fraction:p.processed/p.total})});}
      check();onProgress({stage:'uploading',fraction:0});
      job=await request('begin','bill_upload_begin',{filename:file.name,compressed_size:packed.blob.size,as_of:asOf});
      if(typeof job.job_id!=='string')throw Error('The BILL upload was not acknowledged.');
      for(let at=0;at<packed.blob.size;at+=CHUNK){
        const key='chunk:'+at;
        if(!Object.hasOwn(steps.get(key)||{},'reply')){
          const bytes=new Uint8Array(await packed.blob.slice(at,at+CHUNK).arrayBuffer());check();
          await request(key,'bill_upload_chunk',{job_id:job.job_id,index:at/CHUNK,data:base64(bytes)});
        }
        onProgress({stage:'uploading',fraction:Math.min(1,(at+CHUNK)/packed.blob.size)});
      }
      let progress=await request('finish','bill_upload_finish',{job_id:job.job_id});
      if(progress.duplicate&&progress.alreadyCurrent)return progress;
      if(progress.confirmationRequired&&!await confirmRestore(progress))return cancel();
      let restoring=!!progress.confirmationRequired;
      while(progress.state!=='prepared'){
        check();onProgress({stage:'checking',sourceRowCount:progress.sourceRowCount||0,recordCount:progress.recordCount||0});
        if(typeof progress.generation!=='string'||!Number.isInteger(progress.checkpoint)||progress.checkpoint<0)throw Error('The BILL processing checkpoint is incomplete.');
        if(progress.state==='restart_required'){
          if(!await confirmRestart(progress))return cancel();
          progress=await request('restart:'+progress.generation,'bill_prepare_step',{job_id:job.job_id,generation:progress.generation,expected_checkpoint:progress.checkpoint,restart:true});
        }else{
          const prior=progress;
          progress=await request('prepare:'+prior.generation+':'+prior.checkpoint,'bill_prepare_step',{job_id:job.job_id,generation:prior.generation,expected_checkpoint:prior.checkpoint});
          if(progress.state!=='restart_required'&&(progress.generation!==prior.generation||progress.checkpoint<=prior.checkpoint))throw Error('The BILL processing checkpoint did not advance.');
        }
      }
      check();onProgress({stage:'saving'});
      return await request('activate','bill_activate',{job_id:job.job_id,confirm_restore:restoring});
    }catch(error){
      if(error.name==='AbortError'){await cancel();throw error;}
      // A quota rejection at begin explicitly abandons that unseen server job.
      // A user-requested retry must start a new job, not replay an abandoned lease.
      if(error.code==='bill_quota'&&!job){steps.clear();}
      error.retry=execute;throw error;
    }
  }
  return execute();
}
