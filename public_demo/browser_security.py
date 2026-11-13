"""Network, storage, tab isolation, reload, and framing checks."""
import asyncio
import json
import urllib.request

import websockets

from browser_support import CDP
from browser_differential import differential

async def check_security(c, url, port, attacker_url, unprotected_url, state):
    # Inspect browser-level traffic before intentionally provoking CSP violations.
    await c.js('true')
    observed = [e['params']['request'] for e in c.events if e.get('method') == 'Network.requestWillBeSent']
    allowed = {url, url.rsplit('/', 1)[0] + '/app.js', url.rsplit('/', 1)[0] + '/styles.css', url.rsplit('/', 1)[0] + '/favicon.ico'}
    assert observed and all(r['url'] in allowed and r['method'] == 'GET' for r in observed), observed
    assert all(not any(k.lower() in ('authorization', 'cookie') for k in r['headers']) for r in observed), observed
    assert await c.js("localStorage.length === 0 && sessionStorage.length === 0 && document.cookie === ''")
    assert await c.js("caches.keys().then(x => x.length === 0)")
    assert await c.js("indexedDB.databases().then(x => x.length === 0)")
    # CSP denies runtime connections and inline scripts; these must fail without an HTTP request.
    blocked = await c.js("fetch('/should-not-be-requested').then(()=>false,()=>true)")
    assert blocked, 'CSP did not block fetch'
    assert await c.js("(() => {let s=document.createElement('script'); s.textContent='window.inlineRan=true'; document.body.appendChild(s); return !window.inlineRan})()")
    assert await c.js("new Promise(resolve => {const img=new Image(); img.onload=()=>resolve(false); img.onerror=()=>resolve(true); img.src='/blocked-image';})")
    assert await c.js("new Promise(resolve => {const ws=new WebSocket('ws://' + location.host + '/blocked-ws'); ws.onopen=()=>{ws.close(); resolve(false)}; ws.onerror=()=>resolve(true)})")
    assert await c.js("!document.querySelector('img') && !window.inlineRan")
    # Each tab starts separately; no storage and reloading discards the account.
    tab = json.load(urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/json/new?{url}', method='PUT')))
    async with websockets.connect(tab['webSocketDebuggerUrl']) as ws2:
        second = CDP(ws2)
        for _ in range(100):
            if await second.js("document.readyState === 'complete' && !!document.querySelector('#cash')"):
                break
            await asyncio.sleep(.05)
        assert await second.js("document.querySelector('#cash').textContent") == '$10,000.00'
        assert await second.js("document.querySelector('#shares').textContent") == '0'
        await second.js("document.querySelector('#order-form').requestSubmit()")
        assert await second.js("document.querySelector('#cash').textContent") == '$9,809.98'
        assert await second.js("document.querySelector('#shares').textContent") == '1'
        assert (await state())['rows'] == 1000
    await c.call('Page.reload')
    for _ in range(100):
        if await c.js("document.readyState === 'complete' && document.querySelector('#cash')?.textContent === '$10,000.00'"):
            break
        await asyncio.sleep(.05)
    else:
        raise AssertionError('Reload did not reset state')
    await differential(c)
    frame_tab = json.load(urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{port}/json/new?{attacker_url}', method='PUT')))
    async with websockets.connect(frame_tab['webSocketDebuggerUrl']) as frame_ws:
        frame = CDP(frame_ws)
        await frame.call('Page.enable')
        for _ in range(100):
            tree = await frame.call('Page.getFrameTree')
            children = tree['frameTree'].get('childFrames', [])
            urls = [child['frame']['url'] for child in children]
            if len(urls) == 2 and unprotected_url in urls and any(x.startswith('chrome-error:') for x in urls):
                break
            await asyncio.sleep(.05)
        else:
            raise AssertionError(f'Framing protection or unprotected control failed: {urls}')
    print('PASS: protected page blocks framing; meta-only page is frameable')
    print('PASS: initial state, responsive viewport, buy/sell accounting, exact limits, validation, rejection, CSP, tab isolation and reload reset')
