export function bindStatementDropzone(zone,{canUpload,onFiles,onError}){
  if(!zone)return;
  zone.addEventListener('dragover',event=>{event.preventDefault();if(canUpload()){zone.classList.add('dragging');if(event.dataTransfer)event.dataTransfer.dropEffect='copy';}});
  zone.addEventListener('dragleave',event=>{if(!zone.contains(event.relatedTarget))zone.classList.remove('dragging');});
  zone.addEventListener('drop',async event=>{event.preventDefault();zone.classList.remove('dragging');if(!canUpload())return;try{await onFiles(event.dataTransfer?.files||[]);}catch(error){onError(error);}});
}
