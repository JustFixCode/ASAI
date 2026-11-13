"""Order validation, accounting, and bounded-history browser checks."""
import asyncio
import json

async def check_orders(c):
    snap = "JSON.stringify({cash:document.querySelector('#cash').textContent, shares:document.querySelector('#shares').textContent, total:document.querySelector('#total').textContent, message:document.querySelector('#message').textContent, rows:document.querySelectorAll('#order-rows tr').length})"
    async def state():
        return json.loads(await c.js(snap))
    async def order(side, quantity, limit):
        return await c.js("""(() => { document.querySelector('#side').value = %s; document.querySelector('#quantity').value = %s; document.querySelector('#limit').value = %s; document.querySelector('#order-form').requestSubmit(); return document.querySelector('#message').textContent; })()""" % tuple(json.dumps(x) for x in (side, quantity, limit)))
    # Real keystrokes/paste must not silently truncate invalid input into a valid order.
    await c.js("document.querySelector('#limit').focus(); document.querySelector('#limit').select()")
    await c.call('Input.insertText', {'text':'1000000.000000001'})
    actual_limit = await c.js("document.querySelector('#limit').value")
    assert actual_limit == '1000000.000000001', f'Price silently truncated: {actual_limit!r}'
    await c.js("document.querySelector('#order-form').requestSubmit()")
    assert 'Enter a limit' in (await state())['message']
    await c.js("document.querySelector('#quantity').focus(); document.querySelector('#quantity').select()")
    await c.call('Input.insertText', {'text':'10000001'})
    assert await c.js("document.querySelector('#quantity').value") == '10000001'
    await c.js("document.querySelector('#order-form').requestSubmit()")
    assert 'whole-share' in (await state())['message']
    await c.call('Page.reload')
    for _ in range(100):
        if await c.js("document.readyState === 'complete' && document.querySelector('#message')?.textContent === ''"):
            break
        await asyncio.sleep(.05)
    else:
        raise AssertionError('Reload after input test did not complete')
    initial = await state()
    assert initial == {'cash':'$10,000.00','shares':'0','total':'$10,000.00','message':'','rows':0}, initial
    assert await c.js('document.documentElement.scrollWidth <= innerWidth'), 'mobile overflow'
    assert 'not marketable' in await order('BUY', '1', '190.01999999')
    assert 'not enough' in (await order('SELL', '1', '190')).lower()
    assert 'not enough' in (await order('BUY', '53', '190.02')).lower()
    for quantity in ['0', '-1', '1.5', '1e2', '1000001', '0001']:
        assert 'whole-share' in await order('BUY', quantity, '190.02'), quantity
    for limit in ['0', '-1', '1e2', 'NaN', '190.020000000', '1000000.00000001', '<img src=x>']:
        assert 'Enter a limit' in await order('BUY', '1', limit), limit
    assert (await state())['cash'] == '$10,000.00' and (await state())['rows'] == 0
    assert 'filled at $190.02' in await order('BUY','2','190.02000000')
    assert await state() == {'cash':'$9,619.96','shares':'2','total':'$9,999.96','message':'Simulated buy filled at $190.02 per share.','rows':1}
    assert 'not marketable' in await order('SELL','1','190.00000001')
    assert 'not enough' in (await order('SELL','3','190')).lower()
    assert 'filled at $190.00' in await order('SELL','1','190')
    assert await state() == {'cash':'$9,809.96','shares':'1','total':'$9,999.96','message':'Simulated sell filled at $190.00 per share.','rows':2}
    assert 'filled' in await order('BUY','1','1000000')
    assert await c.js("[...document.querySelectorAll('#order-rows tr')].map(x=>x.children[1].textContent).join(',')") == 'BUY,SELL,BUY'
    # Exercise the bounded history and ensure the 1,001st fill fails without mutation.
    limit_result = await c.js("""(() => {
          const form=document.querySelector('#order-form'), side=document.querySelector('#side'),
                qty=document.querySelector('#quantity'), price=document.querySelector('#limit');
          qty.value='1';
          for (let i=3; i<1000; i++) {
            side.value=i % 2 ? 'SELL' : 'BUY'; price.value=i % 2 ? '190' : '190.02';
            form.requestSubmit();
          }
          const before=[document.querySelector('#cash').textContent, document.querySelector('#shares').textContent];
          side.value='BUY'; price.value='190.02'; form.requestSubmit();
          return {rows:document.querySelectorAll('#order-rows tr').length, before,
                  after:[document.querySelector('#cash').textContent,document.querySelector('#shares').textContent],
                  message:document.querySelector('#message').textContent};
        })()""")
    assert limit_result['rows'] == 1000 and limit_result['before'] == limit_result['after'], limit_result
    assert '1,000-fill' in limit_result['message'], limit_result
    return state
