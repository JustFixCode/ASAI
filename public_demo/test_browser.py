"""Headless Chromium integration tests. Run: python3 public_demo/test_browser.py
Requires Chromium, Python websockets and PyYAML; no third-party service is used.
"""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

import websockets

sys.dont_write_bytecode = True
from browser_support import ROOT, Handler, AttackerHandler, CDP, requests
from browser_ux import ux_review
from browser_orders import check_orders
from browser_security import check_security

async def run(url, port, attacker_url, unprotected_url):
    tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list'))
    async with websockets.connect(tabs[0]['webSocketDebuggerUrl'], max_size=8_000_000) as ws:
        c = CDP(ws)
        await c.call('Page.enable')
        await c.call('Runtime.enable')
        await c.call('Network.enable')
        await c.call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
        await c.call('Page.navigate', {'url': url})
        for _ in range(100):
            if await c.js("document.readyState === 'complete' && !!document.querySelector('#order-form')"):
                break
            await asyncio.sleep(.05)
        else:
            raise AssertionError('Page did not load')
        await ux_review(c)
        state = await check_orders(c)
        await check_security(c, url, port, attacker_url, unprotected_url, state)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT)))
    bare = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(ROOT)))
    attacker = ThreadingHTTPServer(('127.0.0.1', 0), AttackerHandler)
    url = f'http://127.0.0.1:{server.server_port}/index.html'
    bare_url = f'http://127.0.0.1:{bare.server_port}/index.html'
    attacker.targets = [url, bare_url]
    for service in (server, bare, attacker):
        threading.Thread(target=service.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='asai-chromium-') as profile:
        proc = subprocess.Popen(['chromium', '--headless', '--no-sandbox', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            active = Path(profile) / 'DevToolsActivePort'
            for _ in range(200):
                if active.exists():
                    break
                if proc.poll() is not None:
                    raise RuntimeError('Chromium exited')
                time.sleep(.05)
            port = int(active.read_text().splitlines()[0])
            asyncio.run(run(url, port, f'http://127.0.0.1:{attacker.server_port}/', bare_url))
            paths = {path for path, _ in requests}
            assert paths <= {'/index.html', '/styles.css', '/app.js', '/favicon.ico'}, requests
            assert all('Cookie' not in h and 'Authorization' not in h for _, h in requests), requests
            print('PASS: local HTTP requests limited to page and static assets:', sorted(paths))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            for service in (server, bare, attacker):
                service.shutdown()
                service.server_close()

if __name__ == '__main__':
    main()
