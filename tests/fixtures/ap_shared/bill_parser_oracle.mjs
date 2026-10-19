import {importBillSource} from '../../../app/ap_statements/frontend/bill-import.mjs';
import {vendorKey,invoiceKey,cents,dateISO} from '../../../app/ap_statements/frontend/core.mjs';
let text='';for await(const chunk of process.stdin)text+=chunk;
if(process.argv.includes('--keys')){const values=JSON.parse(text);process.stdout.write(JSON.stringify(values.map(value=>({vendor:vendorKey(value),reference:invoiceKey(value),amount:cents(value),date:dateISO(value)}))));}
else process.stdout.write(JSON.stringify(importBillSource(text)));
