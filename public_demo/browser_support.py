"""Local HTTP handlers, Render configuration checks, and Chrome DevTools client."""
import json
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parent

blueprint = yaml.safe_load((ROOT / 'render.yaml').read_text())['services'][0]
assert blueprint['runtime'] == 'static' and blueprint['staticPublishPath'] == './public_demo/dist'
with tempfile.TemporaryDirectory(prefix='asai-build-') as tmp:
    staged = Path(tmp) / 'public_demo'
    shutil.copytree(ROOT, staged)
    subprocess.run(blueprint['buildCommand'], shell=True, cwd=tmp, check=True)
    assert {p.name for p in (staged / 'dist').iterdir()} == {'index.html', 'app.js', 'styles.css'}
    for name in ('index.html', 'app.js', 'styles.css'):
        assert (staged / 'dist' / name).read_bytes() == (ROOT / name).read_bytes()
headers = {item['name']: item['value'] for item in blueprint['headers'] if item['path'] == '/*'}
assert "frame-ancestors 'none'" in headers['Content-Security-Policy']
assert headers['X-Frame-Options'] == 'DENY'
assert headers['X-Content-Type-Options'] == 'nosniff'
requests = []

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def end_headers(self):
        # Simulate the configured Render response headers locally, not Render itself.
        for name, value in headers.items():
            self.send_header(name, value)
        super().end_headers()
    def do_GET(self):
        requests.append((self.path, dict(self.headers)))
        super().do_GET()

class AttackerHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        html = ('<!doctype html><title>Framing test</title>' + ''.join(
            f'<iframe src="{target}"></iframe>' for target in self.server.targets)).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(html)))
        self.end_headers()
        self.wfile.write(html)

class CDP:
    def __init__(self, ws):
        self.ws, self.counter, self.events = ws, 0, []
    async def call(self, method, params=None):
        self.counter += 1
        current = self.counter
        await self.ws.send(json.dumps({'id': current, 'method': method, 'params': params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get('id') == current:
                if 'error' in msg:
                    raise AssertionError(msg['error'])
                return msg['result']
            if 'method' in msg:
                self.events.append(msg)
    async def js(self, code):
        result = await self.call('Runtime.evaluate', {'expression': code, 'returnByValue': True, 'awaitPromise': True})
        if 'exceptionDetails' in result:
            raise AssertionError(result['exceptionDetails'])
        return result['result'].get('value')
