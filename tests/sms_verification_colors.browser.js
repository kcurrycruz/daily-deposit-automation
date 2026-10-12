// Read-only browser regression: evaluate on Daily Deposits or its sample
// verification-card preview, with any mix of verified and pending reports.
(() => {
    const cards = [...document.querySelectorAll('.hwfc-sms-validation-card .hwfc-workbook-check')];
    if (cards.length !== 6) throw new Error('Expected the six SMS report cards.');
    const rgb = color => color.match(/[\d.]+/g).slice(0, 3).map(Number);
    const green = color => {
        const [r, g, b] = rgb(color);
        return g > r && g > b;
    };
    const result = cards.map(card => {
        const style = getComputedStyle(card);
        const label = card.querySelector('.hwfc-workbook-check-label');
        const verified = card.classList.contains('is-verified');
        if (verified && (!green(style.backgroundColor) || !green(style.borderTopColor)
                || !green(getComputedStyle(label).color)))
            throw new Error('Verified report should have green fill, border, and label: ' + label.textContent);
        if (!verified && rgb(style.backgroundColor).some(value => value !== 255))
            throw new Error('Pending report should retain its neutral white fill: ' + label.textContent);
        if (!label.textContent.trim().startsWith(verified ? '✓' : '•'))
            throw new Error('Report must retain its non-color status indicator.');
        return { label: label.textContent.trim(), verified, background: style.backgroundColor };
    });
    return result;
})()
