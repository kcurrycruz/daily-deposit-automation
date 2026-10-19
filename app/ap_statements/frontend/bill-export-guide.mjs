const shot=(file,alt,caption,compact=false)=>`<figure class="bill-guide-shot ${compact?'compact':''}"><img src="./assets/bill-export/${file}" alt="${alt}"><figcaption>${caption}</figcaption></figure>`;
const steps=[
  {title:'Open Settings in BILL',body:'Sign in to BILL. In the left menu, scroll down and select <strong>Settings</strong>.',
    visual:shot('settings.png','BILL left menu with Settings highlighted','Look for Settings near the bottom of the left menu.',true)},
  {title:'Find the Bills export',body:'Open <strong>Import &amp; Export → Legacy Import/Export</strong>. In the <strong>Bills</strong> row, choose <strong>Export</strong> — not Import.',
    visual:shot('legacy-menu.png','Import & Export menu with Legacy Import/Export highlighted','1. Open Legacy Import/Export.',true)+shot('bills-export.png','Bills row with Export highlighted','2. Choose Export on the Bills row.')},
  {title:'Download all bills',body:'Leave the export profile on <strong>Default Mapping</strong>, then click <strong>Export all</strong>. Wait for the CSV download to finish.',
    visual:shot('export-all.png','Default Mapping selected and Export all highlighted','Use Export all to include paid, unpaid and older bills.')},
  {title:'Upload your downloaded CSV',body:'Return to this app and choose the original <strong>BILL CSV</strong> you just downloaded. There is no need to edit it in Excel or upload a separate vendor export.',
    visual:'<div class="bill-guide-ready"><span aria-hidden="true">↓</span><strong>Your Bills CSV is ready</strong><p>Choose it from your Downloads folder.</p></div>'}
];
export function billExportGuideHTML(requestedStep=0){
  const number=Number(requestedStep);
  const index=Number.isFinite(number)?Math.max(0,Math.min(steps.length-1,Math.trunc(number))):0;
  const step=steps[index],last=index===steps.length-1;
  return `<div class="overlay modal-overlay"><section class="modal bill-export-guide" role="dialog" aria-modal="true" aria-labelledby="bill-guide-title">
    <header class="bill-guide-header"><div><div class="eyebrow">Weekly BILL refresh</div><h2 id="bill-guide-title">Update BILL data</h2></div><button class="close" data-action="close" aria-label="Close export guide">×</button></header>
    <div class="bill-guide-progress"><span>Step ${index+1} of ${steps.length}</span><ol aria-label="Export guide progress">${steps.map((_,i)=>`<li class="${i<=index?'complete':''}" ${i===index?'aria-current="step"':''}><span class="sr-only">Step ${i+1}</span></li>`).join('')}</ol></div>
    <div class="bill-guide-body"><h3 data-guide-title tabindex="-1">${step.title}</h3><p>${step.body}</p>${step.visual}
      ${last?'<p class="bill-guide-caution">Your current BILL data stays in place until a new CSV is successfully imported. Updating replaces the comparison source and resets invoice review decisions; notes, original PDFs and completed history remain saved.</p>':'<p class="bill-guide-hint">Follow these steps in BILL, then return here. No API access is needed.</p>'}
    </div>
    <footer class="bill-guide-actions">${!last?'<button class="button subtle" data-action="bill-guide-upload">I already have the CSV</button>':'<span></span>'}<div class="action-row">${index? `<button class="button" data-action="bill-guide-step" data-step="${index-1}">Back</button>`:''}${last?'<button class="button primary" data-action="bill-guide-upload">Upload downloaded CSV</button>':`<button class="button primary" data-action="bill-guide-step" data-step="${index+1}">Next →</button>`}</div></footer>
  </section></div>`;
}
