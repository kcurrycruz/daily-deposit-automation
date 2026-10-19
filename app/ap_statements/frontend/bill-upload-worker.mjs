const MAX_SOURCE=256*1024*1024,MAX_PACKED=32*1024*1024;
export async function compressBillFile(file,{onProgress=()=>{}}={}){
  if(!Number.isInteger(file?.size)||file.size<1||file.size>MAX_SOURCE)throw Error('Choose a CSV no larger than 256 MiB.');
  if(typeof CompressionStream!=='function'||typeof TransformStream!=='function')throw Error('This browser needs streaming compression support to prepare BILL exports.');
  let read=0,last=0,total=0;
  const input=file.stream().pipeThrough(new TransformStream({transform(chunk,controller){
    read+=chunk.byteLength;if(read>file.size||read>MAX_SOURCE)throw Error('The BILL source size could not be verified.');
    controller.enqueue(chunk);if(read-last>=4*1024*1024||read===file.size){last=read;onProgress({processed:read,total:file.size});}
  }})).pipeThrough(new CompressionStream('gzip'));
  const reader=input.getReader(),parts=[];
  try{
    while(true){const {done,value}=await reader.read();if(done)break;total+=value.byteLength;
      if(total>MAX_PACKED)throw Error('The compressed BILL export exceeds the 32 MiB upload size limit.');parts.push(value);}
    if(read!==file.size)throw Error('The BILL source size could not be verified.');
    return {blob:new Blob(parts,{type:'application/gzip'}),originalBytes:read};
  }catch(error){await reader.cancel().catch(()=>{});throw error;}
  finally{reader.releaseLock();}
}
if(typeof WorkerGlobalScope!=='undefined'&&globalThis instanceof WorkerGlobalScope){
  globalThis.onmessage=async({data})=>{
    if(data?.type!=='compress'||typeof data.id!=='string')return;
    try{const result=await compressBillFile(data.file,{onProgress:progress=>postMessage({id:data.id,type:'progress',progress})});postMessage({id:data.id,type:'result',...result});}
    catch(error){postMessage({id:data.id,type:'error',message:error.message||'BILL export preparation failed.'});}
  };
}
