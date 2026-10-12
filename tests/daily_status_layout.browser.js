// Evaluate this read-only function in the rendered Daily page via browser tools.
// Desktop: run where Files wraps; mobile: verify stacked items remain contained.
(() => {
    const grid = document.querySelector('#hwfc-daily-page') && document.querySelector('.hwfc-ops-status');
    if (!grid) throw new Error('Open Daily Deposits before checking its status row.');
    const items = [...grid.querySelectorAll('.hwfc-ops-status-item')];
    if (items.length !== 3) throw new Error('Expected three status columns.');
    const geometry = items.map(item => {
        const label = item.querySelector('.hwfc-ops-status-label');
        const value = item.querySelector('.hwfc-ops-status-value');
        const bar = item.querySelector('.hwfc-ops-progress');
        const bounds = item.getBoundingClientRect();
        const progress = bar.getBoundingClientRect();
        const text = document.createRange();
        text.selectNodeContents(value);
        if (progress.bottom > bounds.bottom + 1 || value.scrollWidth > value.clientWidth + 1)
            throw new Error('Status text or progress overflows its column.');
        return { label: label.textContent, labelTop: label.getBoundingClientRect().top,
            valueTop: value.getBoundingClientRect().top, valueHeight: value.getBoundingClientRect().height,
            textLines: [...text.getClientRects()].filter(rect => rect.width > 0).length,
            barTop: progress.top, itemTop: bounds.top, itemBottom: bounds.bottom };
    });
    const spread = key => Math.max(...geometry.map(item => item[key])) - Math.min(...geometry.map(item => item[key]));
    const horizontal = spread('itemTop') < 1;
    if (horizontal && geometry.find(item => item.label === 'Files').textLines < 2)
        throw new Error('Use a desktop width where Files wraps to exercise this regression.');
    if (horizontal && (spread('barTop') > 1 || spread('labelTop') > 1 || spread('valueTop') > 1))
        throw new Error('Status row is not aligned: ' + JSON.stringify(geometry));
    return { horizontal, geometry };
})()
