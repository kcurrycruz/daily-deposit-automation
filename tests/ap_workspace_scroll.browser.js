// Run read-only inside the AP component frame using browser tools, with
// synthetic statements loaded. Streamlit sets scrolling="no" on that frame.
// Separately wheel-scroll over the workspace and confirm main.scrollTop grows.
(() => {
    const main = document.querySelector('.main');
    if (!main) throw new Error('Open the AP workspace before checking scrolling.');
    const sidebar = document.querySelector('.sidebar');
    if (sidebar.scrollWidth > sidebar.clientWidth + 1)
        throw new Error('Sidebar navigation overflows horizontally.');
    const bounds = main.getBoundingClientRect();
    const style = getComputedStyle(main);
    if (!['auto', 'scroll'].includes(style.overflowY))
        throw new Error('AP content must have its own vertical scroll container.');
    if (bounds.top < -1 || bounds.bottom > innerHeight + 1 || main.clientHeight < 100)
        throw new Error('AP scroll container must fit the available viewport.');
    if (main.scrollHeight <= main.clientHeight)
        throw new Error('Load enough synthetic statements to exercise overflow.');
    const footer = main.querySelector('.table-foot');
    if (!footer) throw new Error('Expected statement list footer.');
    const atBottom = Math.abs(main.scrollHeight - main.clientHeight - main.scrollTop) < 2;
    if (atBottom && footer.getBoundingClientRect().bottom > bounds.bottom + 1)
        throw new Error('Statement list footer remains clipped at the bottom.');
    return { viewport: innerHeight, height: main.clientHeight, content: main.scrollHeight,
        scrollTop: main.scrollTop, atBottom, footerBottom: footer.getBoundingClientRect().bottom };
})()
