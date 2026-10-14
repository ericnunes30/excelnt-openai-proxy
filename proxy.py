import http.server
import urllib.request
import urllib.error
import sys
from typing import Dict, Tuple

class HeaderDecorator:
    EXCLUDED = {'host', 'user-agent', 'content-length'}

    def decorate(self, incoming_headers: http.client.HTTPMessage) -> Dict[str, str]:
        forwarded = {
            k: v for k, v in incoming_headers.items() 
            if k.lower() not in self.EXCLUDED
        }
        forwarded['User-Agent'] = 'Excelnt/1.0.24'
        forwarded['HTTP-Referer'] = 'https://github.com/ExcelntVetGit/Excelnt-Excelnt'
        forwarded['X-Title'] = 'Excelnt'
        return forwarded

class UrlResolver:
    def __init__(self, target_base: str):
        self._target_base = target_base.rstrip('/')

    def resolve(self, path: str) -> str:
        clean_path = path[3:] if path.startswith('/v1/') else path
        if clean_path.startswith('/'):
            return f"{self._target_base}{clean_path}"
        return f"{self._target_base}/{clean_path}"

class UpstreamForwarder:
    def __init__(self, decorator: HeaderDecorator, resolver: UrlResolver):
        self._decorator = decorator
        self._resolver = resolver

    def forward(self, method: str, path: str, headers: http.client.HTTPMessage, body: bytes):
        target_url = self._resolver.resolve(path)
        out_headers = self._decorator.decorate(headers)
        if body and 'content-type' not in [k.lower() for k in out_headers]:
            out_headers['Content-Type'] = 'application/json'
        return urllib.request.Request(target_url, data=body, headers=out_headers, method=method)

class ProxyStreamer:
    def __init__(self, wfile):
        self._wfile = wfile

    def pipe(self, response_stream):
        while True:
            chunk = response_stream.read(1024)
            if not chunk:
                break
            self._wfile.write(chunk)
            self._wfile.flush()

class ExcelntProxyHandler(http.server.BaseHTTPRequestHandler):
    forwarder = UpstreamForwarder(
        HeaderDecorator(),
        UrlResolver("https://excelnt.ai/v1")
    )

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method: str):
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len > 0 else None
        req = self.forwarder.forward(method, self.path, self.headers, body)
        streamer = ProxyStreamer(self.wfile)

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                self._copy_headers(resp.headers)
                self.end_headers()
                streamer.pipe(resp)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self._copy_headers(e.headers)
            self.end_headers()
            self.wfile.write(e.read())
            self.wfile.flush()
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(f'{{"error": "{str(e)}"}}'.encode('utf-8'))

    def _copy_headers(self, headers):
        excluded = {'transfer-encoding', 'content-encoding', 'content-length'}
        for k, v in headers.items():
            if k.lower() not in excluded:
                self.send_header(k, v)
        self.send_header('Access-Control-Allow-Origin', '*')

    def log_message(self, format, *args):
        sys.stderr.write(f"[Proxy] {args[0]} {args[1]} -> {args[2]}\n")

def run(port: int = 5050):
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), ExcelntProxyHandler)
    print(f"==================================================")
    print(f"   PROXY EXCELNT AI ATIVO EM: http://127.0.0.1:{port}/v1")
    print(f"==================================================")
    print(f"Configure o Base URL no Pencil/Cursor/etc como:")
    print(f"http://127.0.0.1:{port}/v1\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy finalizado.")

if __name__ == '__main__':
    run()
