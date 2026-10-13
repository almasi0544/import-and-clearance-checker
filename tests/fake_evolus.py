"""A tiny local web server that stands in for Evolus, so the client can be tested without
an API key, credits or internet."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class FakeEvolus:
    def __init__(self, responses=None, handler=None):
        self.requests = []                      # every request received
        self._responses = list(responses or [])  # list of (status, body, headers)
        self._handler = handler                  # or a function(request) -> (status, body)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the test output quiet
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                request = {"path": self.path.split("?")[0], "query": self.path.partition("?")[2],
                           "headers": {k.lower(): v for k, v in self.headers.items()}, "body": self.rfile.read(length)}
                outer.requests.append(request)
                headers = {}
                if outer._handler:
                    status, body = outer._handler(request)
                else:
                    status, body, headers = outer._next()
                payload = body if isinstance(body, (bytes, str)) else json.dumps(body)
                payload = payload.encode() if isinstance(payload, str) else payload
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(payload)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/api/v1"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def _next(self):
        item = self._responses.pop(0) if len(self._responses) > 1 else (self._responses[0] if self._responses else (200, {}, {}))
        status, body = item[0], item[1]
        return status, body, (item[2] if len(item) > 2 else {})

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
