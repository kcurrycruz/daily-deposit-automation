import {extractPDF,stopOCR} from '/frontend/extraction.mjs';
window.extractStatement=async(data,filename,options={maxRasterPixels:20_000_000})=>{
 const bytes=Uint8Array.from(atob(data),value=>value.charCodeAt(0));
 try{return await extractPDF(new File([bytes],filename,{type:'application/pdf'}),
  value=>window.reportScanProgress?.({page:value.page,total:value.total,stage:value.stage}),options);}
 finally{await stopOCR();}
};
