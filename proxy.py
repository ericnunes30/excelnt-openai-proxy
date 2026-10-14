import http.server
import urllib.request
import urllib.error
import json
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

class EnvLoader:
    @staticmethod
    def load(env_filename: str = ".env"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        paths = [os.path.join(script_dir, env_filename), os.path.join(os.getcwd(), env_filename)]
        for p in paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        clean = line.strip()
                        if clean and not clean.startswith("#") and "=" in clean:
                            key, val = clean.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip("'\"")
                            if key and key not in os.environ:
                                os.environ[key] = val
                break

class HeaderDecorator:
    EXCLUDED = {'host', 'user-agent', 'content-length'}

    def decorate(self, incoming_headers: http.client.HTTPMessage) -> Dict[str, str]:
        forwarded = {
            k: v for k, v in incoming_headers.items() 
            if k.lower() not in self.EXCLUDED
        }
        forwarded['User-Agent'] = 'Excelnt/1.0.24'
        forwarded['originator'] = 'excelnt'
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

class SystemInstructionInjector:
    DEFAULT_INSTRUCTION = "Responda SEMPRE no chat em Português do Brasil (PT-BR) para o usuário."

    def __init__(self):
        self._instruction = os.environ.get("EXCELNT_SYSTEM_INSTRUCTION", self.DEFAULT_INSTRUCTION).strip()

    def inject(self, payload_dict: dict) -> dict:
        if not self._instruction or "messages" not in payload_dict:
            return payload_dict
        messages = payload_dict.get("messages", [])
        if not isinstance(messages, list):
            return payload_dict

        system_msg = next((m for m in messages if isinstance(m, dict) and m.get("role") == "system"), None)
        if system_msg and isinstance(system_msg.get("content"), str):
            system_msg["content"] += f"\n\n[Regra de Comunicação]: {self._instruction}"
        else:
            messages.insert(0, {"role": "system", "content": f"[Regra de Comunicação]: {self._instruction}"})
        return payload_dict

class ModelFallbackManager:
    DEFAULT_FALLBACKS = [
        "deepseek-v4.1-flash",
        "mimo-v2.6-flash",
        "mimo-v2.6-pro",
        "glm-5.3-flash",
        "ling-flash-3.1",
        "mimo-v2.5",
        "gemini-3.7-flash",
        "claude-sonnet-4-6"
    ]

    def __init__(self):
        env_raw = os.environ.get("EXCELNT_FALLBACK_MODELS", "")
        if env_raw.strip():
            self._models = [m.strip() for m in env_raw.split(",") if m.strip()]
        else:
            self._models = self.DEFAULT_FALLBACKS

    def get_candidate_chain(self, primary_model: str) -> List[str]:
        candidates = [primary_model] if primary_model else []
        for m in self._models:
            if m not in candidates:
                candidates.append(m)
        return candidates

class UpstreamForwarder:
    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(self, decorator: HeaderDecorator, resolver: UrlResolver, 
                 injector: SystemInstructionInjector, fallback_mgr: ModelFallbackManager):
        self._decorator = decorator
        self._resolver = resolver
        self._injector = injector
        self._fallback_mgr = fallback_mgr
        self._max_fallbacks = int(os.environ.get("EXCELNT_MAX_FALLBACKS", "5"))

    def forward(self, method: str, path: str, headers: http.client.HTTPMessage, raw_body: bytes):
        target_url = self._resolver.resolve(path)
        out_headers = self._decorator.decorate(headers)
        if raw_body and 'content-type' not in [k.lower() for k in out_headers]:
            out_headers['Content-Type'] = 'application/json'

        # Only apply fallback and instruction injection to chat/completions JSON bodies
        if method == "POST" and "chat/completions" in path and raw_body:
            return self._forward_with_fallback(target_url, out_headers, raw_body)
        
        req = urllib.request.Request(target_url, data=raw_body, headers=out_headers, method=method)
        return urllib.request.urlopen(req, timeout=60)

    def _forward_with_fallback(self, target_url: str, headers: Dict[str, str], raw_body: bytes):
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except Exception:
            req = urllib.request.Request(target_url, data=raw_body, headers=headers, method="POST")
            return urllib.request.urlopen(req, timeout=60)

        payload = self._injector.inject(payload)
        original_model = payload.get("model", "")
        candidates = self._fallback_mgr.get_candidate_chain(original_model)[:self._max_fallbacks + 1]

        last_error = None
        for idx, model in enumerate(candidates):
            payload["model"] = model
            body_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(target_url, data=body_bytes, headers=headers, method="POST")
            try:
                if idx > 0:
                    sys.stderr.write(f"[Proxy Fallback] Testando modelo alternativo: '{model}'...\n")
                resp = urllib.request.urlopen(req, timeout=60)
                if idx > 0:
                    sys.stderr.write(f"[Proxy Fallback] Sucesso com o modelo '{model}'!\n")
                return resp
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code in self.RETRY_STATUSES and idx < len(candidates) - 1:
                    sys.stderr.write(f"[Proxy Fallback] Modelo '{model}' falhou com HTTP {e.code}. Tentando proximo...\n")
                    time.sleep(0.5)
                    continue
                raise e
            except Exception as e:
                last_error = e
                if idx < len(candidates) - 1:
                    sys.stderr.write(f"[Proxy Fallback] Erro na conexao com '{model}': {e}. Tentando proximo...\n")
                    time.sleep(0.5)
                    continue
                raise e
        raise last_error

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
    forwarder = None  # Initialized in run()

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
        streamer = ProxyStreamer(self.wfile)

        try:
            resp = self.forwarder.forward(method, self.path, self.headers, body)
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

def run():
    EnvLoader.load()
    port = int(os.environ.get("EXCELNT_PORT", "5050"))
    ExcelntProxyHandler.forwarder = UpstreamForwarder(
        HeaderDecorator(),
        UrlResolver("https://excelnt.ai/v1"),
        SystemInstructionInjector(),
        ModelFallbackManager()
    )
    fallback_mgr = ModelFallbackManager()
    print("==================================================")
    print(f"   PROXY EXCELNT AI ATIVO EM: http://127.0.0.1:{port}/v1")
    print(f"   [Fallback Automatico de Modelos: ATIVADO]")
    print(f"   Modelos na fila: {', '.join(fallback_mgr._models)}")
    print("==================================================")
    print(f"Configure o Base URL no Pencil/Cursor/etc como:")
    print(f"http://127.0.0.1:{port}/v1\n")

    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), ExcelntProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nProxy finalizado.")

if __name__ == '__main__':
    run()
