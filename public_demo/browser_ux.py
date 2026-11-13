"""Responsive layout, accessibility, and contrast checks."""
import asyncio

async def ux_review(c):
    # Check every rendered text-bearing element against its nearest opaque background.
    # All page colors are opaque; anti-aliasing and browser UI are not assessed here.
    async def check_contrast():
        failures = await c.js(r'''(() => {
          const rgb = s => (s.match(/[\d.]+/g) || []).map(Number);
          const luminance = color => color.slice(0, 3).map(v => {
            v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
          return [...document.querySelectorAll('body *')].filter(el => {
            const text = [...el.childNodes].some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
            const control = el.matches('input,select');
            return (text || control) && !el.closest('.sr-only') && el.getClientRects().length && getComputedStyle(el).visibility === 'visible';
          }).map(el => {
            const fg = rgb(getComputedStyle(el).color);
            let node = el, bg;
            while (node) {
              const color = rgb(getComputedStyle(node).backgroundColor);
              if (color.length >= 3 && (color.length < 4 || color[3] === 1)) { bg = color; break; }
              node = node.parentElement;
            }
            bg ||= [255,255,255];
            const a = luminance(fg), b = luminance(bg);
            return {element: el.tagName + (el.id ? '#'+el.id : '') + (el.className ? '.'+String(el.className).replace(/\s+/g,'.') : ''), text: el.textContent.trim().slice(0,60), ratio: (Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
          }).filter(x => x.ratio < 4.5);
        })()''')
        assert not failures, f'Text contrast under 4.5:1: {failures}'

    async def click_submit():
        point = await c.js('''(() => {const b=document.querySelector('button[type=submit]');
          b.scrollIntoView({block:'center'}); const r=b.getBoundingClientRect();
          return {x:r.left+r.width/2,y:r.top+r.height/2}})()''')
        await c.call('Input.dispatchMouseEvent', {'type':'mousePressed', **point, 'button':'left', 'clickCount':1})
        await c.call('Input.dispatchMouseEvent', {'type':'mouseReleased', **point, 'button':'left', 'clickCount':1})
        visible = await c.js('''(() => {const r=document.querySelector('#message').getBoundingClientRect();
          return r.top >= 0 && r.bottom <= innerHeight && r.left >= 0 && r.right <= innerWidth})()''')
        assert visible, 'Order feedback is not fully visible after submitting on mobile'

    await c.call('Emulation.setDeviceMetricsOverride', {'width':320, 'height':568, 'deviceScaleFactor':1, 'mobile':True})
    assert await c.js('document.documentElement.scrollWidth <= innerWidth'), '320px page overflows'
    grid = await c.js('''(() => {const g=document.querySelector('.portfolio-grid'); const gr=g.getBoundingClientRect();
      const cells=[...g.children].map(el => {const r=el.getBoundingClientRect(), s=el.querySelector('strong').getBoundingClientRect();
        return {l:r.left,r:r.right,t:r.top,b:r.bottom,sl:s.left,sr:s.right}});
      return {left:gr.left,right:gr.right,cells}})()''')
    for i, cell in enumerate(grid['cells']):
        assert grid['left'] <= cell['l'] <= cell['sl'] and cell['sr'] <= cell['r'] <= grid['right'], grid
        for other in grid['cells'][i+1:]:
            assert cell['r'] <= other['l'] or other['r'] <= cell['l'] or cell['b'] <= other['t'] or other['b'] <= cell['t'], grid
    assert await c.js("document.querySelector('.simulation-notice').textContent.toLowerCase().includes('not an alpaca paper account') && document.querySelector('.simulation-notice').textContent.toLowerCase().includes('resets on refresh')")
    assert await c.js("document.querySelector('.ticket-context').textContent.includes('Bid') && document.querySelector('.ticket-context').textContent.includes('$190.00') && document.querySelector('.ticket-context').textContent.includes('Ask') && document.querySelector('.ticket-context').textContent.includes('$190.02') && document.querySelector('#ticket-cash').textContent === '$10,000.00'")
    await check_contrast()
    await c.js("document.querySelector('#quantity').value='0'")
    await click_submit()
    assert await c.js("document.querySelector('#quantity').getAttribute('aria-invalid') === 'true' && document.querySelector('#quantity').getAttribute('aria-describedby').split(' ').includes('quantity-error') && document.querySelector('#quantity-error').textContent.includes('whole-share')")
    await check_contrast()
    await c.js("document.querySelector('#quantity').value='1'; document.querySelector('#quantity').dispatchEvent(new Event('input', {bubbles:true})); document.querySelector('#limit').value='0'")
    assert await c.js("!document.querySelector('#quantity').hasAttribute('aria-invalid') && !document.querySelector('#quantity-error').textContent")
    await click_submit()
    assert await c.js("document.querySelector('#limit').getAttribute('aria-invalid') === 'true' && document.querySelector('#limit').getAttribute('aria-describedby').split(' ').includes('limit-error') && document.querySelector('#limit-error').textContent.includes('Enter a limit')")
    await c.js("document.querySelector('#limit').value='190.02'; document.querySelector('#limit').dispatchEvent(new Event('input', {bubbles:true}))")
    await click_submit()
    assert await c.js("document.querySelector('#message').textContent.includes('filled at $190.02') && document.querySelector('#ticket-cash').textContent === '$9,809.98' && document.querySelector('#ticket-cash').textContent === document.querySelector('#cash').textContent && !document.querySelector('[aria-invalid=true]')")
    await check_contrast()
    await c.call('Emulation.setDeviceMetricsOverride', {'width':1200, 'height':900, 'deviceScaleFactor':1, 'mobile':False})
    await check_contrast()
    print('PASS: 320px portfolio geometry, visible mobile rejection and fill feedback, ticket context, field error semantics and computed text contrast')
    await c.call('Emulation.setDeviceMetricsOverride', {'width':390, 'height':844, 'deviceScaleFactor':1, 'mobile':True})
    await c.call('Page.reload')
    for _ in range(100):
        if await c.js("document.readyState === 'complete' && document.querySelector('#cash')?.textContent === '$10,000.00' && document.querySelector('#message')?.textContent === ''"):
            return
        await asyncio.sleep(.05)
    raise AssertionError('Reload after UX checks did not complete')
