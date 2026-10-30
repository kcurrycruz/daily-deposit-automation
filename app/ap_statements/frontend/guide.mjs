import { totals, reconcile } from './core.mjs';

export function emptyWorkspace() {
  return { statements: [], provider: { loaded: false, simulated: false, records: [], label: 'Not connected' } };
}

// Recommendations only: never confirm evidence, save data, or clear reviews.
export function workflowGuide(state) {
  const documents = state.statements;
  const comparisons = documents.flatMap(doc => reconcile(doc, state.provider, state.mappings || {}));
  const unchecked = documents.filter(doc => !doc.confirmed || !doc.rows.length || !doc.vendor.trim()
    || doc.vendor === 'Unidentified vendor' || (totals(doc).difference != null && totals(doc).difference !== 0)
    || comparisons.some(row => row.statementId === doc.id && row.status === 'extraction'));
  const uploaded = documents.length > 0;
  const extracted = uploaded && unchecked.length === 0;
  const sourceReady = extracted && state.provider.loaded && !state.provider.simulated;
  const attention = comparisons.filter(row => row.status !== 'matched' && !state.resolutions?.[row.id]?.decision).length;
  const current = !uploaded ? 'upload' : !extracted ? 'extraction' : !sourceReady ? 'source' : 'review';
  const steps = [
    { id: 'upload', title: 'Upload statements', detail: 'Choose one or more vendor PDFs.', complete: uploaded },
    { id: 'extraction', title: 'Check invoices', detail: 'Verify what was read from each PDF.', complete: extracted },
    { id: 'source', title: 'Compare with BILL', detail: 'Import the Bills CSV and choose active dates. Archived references remain available.', complete: !!sourceReady },
    { id: 'review', title: 'Review & export', detail: 'Record decisions and keep your report.', complete: false },
  ];
  const copy = {
    upload: { heading: 'Upload your first statement', body: 'Start with a vendor statement PDF. You can select several vendors at once. We’ll read the invoices and guide you through checking them.', label: 'Upload statement PDFs' },
    extraction: { heading: 'Check the invoices we read', body: `${unchecked.length} statement${unchecked.length === 1 ? '' : 's'} need a check. Compare the extracted rows with the original PDF, correct anything missing, then confirm the extraction.`, label: 'Check next statement' },
    source: { heading: 'Add your BILL invoice records', body: 'PDFs are ready to compare. Import the original Bills CSV export directly—no template conversion is needed. Without records, the app cannot tell whether an invoice is in BILL.', label: 'Add BILL records' },
    review: { heading: attention ? 'Review the differences' : 'Save your work and export the report', body: attention ? `${attention} item${attention === 1 ? '' : 's'} need attention. Open the evidence and record a decision. Notes are optional. Save changes, mark the statement reviewed with your initials, and export your report.` : 'No unreviewed differences remain. Open a statement to mark it reviewed with your initials, then export its report. A match does not verify QuickBooks sync or complete historical coverage.', label: attention ? 'Review next difference' : 'Export report' },
  };
  return { current, index: steps.findIndex(step => step.id === current), steps,
    documentId: unchecked[0]?.id ?? documents[0]?.id ?? null, attention,
    simulated: !!state.provider.simulated,
    action: current === 'review' ? attention ? 'review' : 'export' : current,
    ...copy[current] };
}
