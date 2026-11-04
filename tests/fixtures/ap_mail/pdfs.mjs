// Synthetic PDF builders: every fixture is generated, never a company original.
import {createHash} from 'node:crypto';
export const statementLines=['A.J. Rinella','DATE: 11/01/26','DATE INVOICE AMOUNT BALANCE',
 '10/28/26 00042 100.00 100.00','10/29/26 00043 200.00 200.00','INVOICE TOTAL 300.00'];
const bytes=value=>Buffer.isBuffer(value)?value:Buffer.from(value,'ascii');
function assemble(objects,trailer=''){
 const chunks=[bytes('%PDF-1.4\n')],offsets=[0];let size=chunks[0].length;
 for(let i=0;i<objects.length;i++){
  offsets.push(size);const object=Buffer.concat([bytes(`${i+1} 0 obj\n`),bytes(objects[i]),bytes('\nendobj\n')]);
  chunks.push(object);size+=object.length;
 }
 chunks.push(bytes(`xref\n0 ${objects.length+1}\n0000000000 65535 f \n${offsets.slice(1).map(n=>String(n).padStart(10,'0')+' 00000 n ').join('\n')}\ntrailer\n<< /Size ${objects.length+1} /Root 1 0 R ${trailer} >>\nstartxref\n${size}\n%%EOF`));
 return Buffer.concat(chunks);
}
export function textPdf(lines=statementLines,{pages=1}={}){
 const escape=s=>s.replace(/[\\()]/g,'\\$&');
 const stream='BT /F1 14 Tf '+lines.map((s,i)=>{
  const y=740-i*35;
  if(i>=2&&i<=4)return s.split(/\s+/).map((value,n)=>`1 0 0 1 ${[90,170,260,480][n]} ${y} Tm (${escape(value)}) Tj`).join('\n');
  return `1 0 0 1 ${i===1?380:40} ${y} Tm (${escape(s)}) Tj`;
 }).join('\n')+' ET';
 const objects=['<< /Type /Catalog /Pages 2 0 R >>',`<< /Type /Pages /Kids [${Array.from({length:pages},(_,i)=>`${4+i*2} 0 R`).join(' ')}] /Count ${pages} >>`,
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
 for(let i=0;i<pages;i++)objects.push(`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents ${5+i*2} 0 R >>`,
  `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
 return assemble(objects);
}
export function imagePdf(jpeg,width,height){
 const stream='q 612 0 0 792 0 0 cm /Im0 Do Q';
 return assemble(['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>',
  Buffer.concat([bytes(`<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpeg.length} >>\nstream\n`),jpeg,bytes('\nendstream')]),
  `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`]);
}

// Legacy PDF standard-security fixture only; never use this cipher for storage.
export function encryptedPdf(){
 const padding=Buffer.from('28bf4e5e4e758a4164004e56fffa01082e2e00b6d0683e802f0ca9fe6453697a','hex');
 const padded=text=>Buffer.concat([Buffer.from(text),padding]).subarray(0,32);
 const md5=data=>createHash('md5').update(data).digest();
 function rc4(key,data){
  const s=Uint8Array.from({length:256},(_,i)=>i);let j=0;
  for(let i=0;i<256;i++){j=(j+s[i]+key[i%key.length])%256;[s[i],s[j]]=[s[j],s[i]];}
  let i=0;j=0;return Buffer.from(data.map(value=>{i=(i+1)%256;j=(j+s[i])%256;[s[i],s[j]]=[s[j],s[i]];return value^s[(s[i]+s[j])%256];}));
 }
 const id=Buffer.alloc(16,7),owner=rc4(md5(padded('owner')).subarray(0,5),padded('secret'));
 const permissions=Buffer.alloc(4);permissions.writeInt32LE(-4);
 const key=md5(Buffer.concat([padded('secret'),owner,permissions,id])).subarray(0,5);
 const user=rc4(key,padding),objectKey=md5(Buffer.concat([key,Buffer.from([5,0,0,0,0])])).subarray(0,10);
 const stream=rc4(objectKey,Buffer.from('BT /F1 14 Tf 40 740 Td (Synthetic private fixture) Tj ET'));
 return assemble(['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',Buffer.concat([bytes(`<< /Length ${stream.length} >>\nstream\n`),stream,bytes('\nendstream')]),
  `<< /Filter /Standard /V 1 /R 2 /O <${owner.toString('hex')}> /U <${user.toString('hex')}> /P -4 >>`],
  `/Encrypt 6 0 R /ID [<${id.toString('hex')}> <${id.toString('hex')}>]`);
}
