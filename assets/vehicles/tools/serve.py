"""Local asset acceptance viewer. Serves this package and GET-only API requests.
No BMW source records are bundled. Existing API access logging remains active.
"""
import argparse
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, default=18460)
parser.add_argument('--api', default='http://127.0.0.1:18000')
args = parser.parse_args()
if urlsplit(args.api).hostname not in ('127.0.0.1', 'localhost', '::1'):
    parser.error('Acceptance viewer API must be loopback.')
root = Path(__file__).resolve().parent.parent

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith('/api/'):
            path = self.path[4:]
            route = urlsplit(path).path
            if not (route == '/requirements' or route.startswith('/requirements/') or route == '/audit'):
                self.send_error(404)
                return
            try:
                with urlopen(Request(args.api.rstrip('/') + path, headers={'Accept': 'application/json'}), timeout=15) as r:
                    body, status = r.read(), r.status
            except HTTPError as error:
                body, status = error.read(), error.code
            except (URLError, TimeoutError):
                body, status = json.dumps({'error': 'BMW API unavailable; no fixture substituted.'}).encode(), 502
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

print(f'Asset viewer: http://127.0.0.1:{args.port}/tools/viewer.html', flush=True)
ThreadingHTTPServer(('127.0.0.1', args.port), functools.partial(Handler, directory=str(root))).serve_forever()
