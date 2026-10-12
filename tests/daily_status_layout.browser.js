// Evaluate this read-only function in the rendered Daily page via browser tools.
// Desktop: verify aligned bars and a compact initial Files summary; mobile:
// verify stacked items remain contained without a lone "needed" line.
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
    const filesValue = items[1].querySelector('.hwfc-ops-status-value');
    if (horizontal && filesValue.clientWidth >= 250 && filesValue.textContent.includes('Card Settlement')
        && filesValue.textContent.includes('needed') && geometry[1].textLines !== 1)
        throw new Error('The compact Files summary should fit on one desktop line.');
    if (filesValue.textContent.includes('needed') && !filesValue.textContent.includes('Settlement\u00a0needed'))
        throw new Error('Keep Settlement and needed together on narrower screens.');
    if (horizontal && (spread('barTop') > 1 || spread('labelTop') > 1 || spread('valueTop') > 1))
        throw new Error('Status row is not aligned: ' + JSON.stringify(geometry));
    return { horizontal, geometry };
})()
