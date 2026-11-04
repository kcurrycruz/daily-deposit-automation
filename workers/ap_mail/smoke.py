"""Offline container acceptance: real bundled PDF reader, sandbox left enabled."""
from pathlib import Path
import tempfile
from app.ap_mail.extraction import extract_private_pdf

def synthetic_pdf():
    lines=['Synthetic Co','DATE: 11/01/26','DATE INVOICE AMOUNT BALANCE','10/28/26 00042 100.00 100.00','10/29/26 00043 200.00 200.00']
    chunks=['BT /F1 14 Tf']
    for n,line in enumerate(lines):
        y=740-n*35
        if 2<=n<=4:chunks.extend(f'1 0 0 1 {x} {y} Tm ({part}) Tj' for x,part in zip([90,170,260,480],line.split()))
        else:chunks.append(f'1 0 0 1 {380 if n==1 else 40} {y} Tm ({line}) Tj')
    content=('\n'.join(chunks)+' ET').encode()
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    out=bytearray(b'%PDF-1.4\n');offsets=[]
    for n,obj in enumerate(objects,1):offsets.append(len(out));out.extend(str(n).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    start=len(out);out.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets:out.extend(f'{offset:010d} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode());return bytes(out)

def main():
    with tempfile.TemporaryDirectory(prefix='ap-mail-smoke-') as folder:
        path=Path(folder)/'synthetic.pdf';path.write_bytes(synthetic_pdf())
        doc=extract_private_pdf(path,'synthetic.pdf',heartbeat=lambda:True)
        if doc['confirmed'] is not False or [(row['invoiceNumber'],row['amount']) for row in doc['rows']]!=[('00042',10000),('00043',20000)]:raise SystemExit('Bundled parser smoke failed.')
    print('AP mail offline browser smoke passed; synthetic data only.')
if __name__=='__main__':main()
