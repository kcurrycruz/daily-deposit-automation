"""Summarize work progress from a frozen revision, never the current BILL import."""


def review_progress(revision):
    rows = revision.get('results')
    if (not revision.get('doc', {}).get('confirmed') or not isinstance(rows, list)
            or not rows or any(not isinstance(row, dict) or not row.get('id')
                               or not isinstance(row.get('status'), str) for row in rows)):
        return None
    resolutions = revision.get('resolutions') or {}
    resolved = 0
    for row in rows:
        decision = resolutions.get(row['id'], {}).get('decision')
        if decision:
            resolved += decision == 'Reviewed — no action needed'
        else:
            resolved += (not row.get('preview') and not row.get('simulated')
                         and row['status'] in ('matched', 'presence'))
    return {'resolved': resolved, 'total': len(rows)}
