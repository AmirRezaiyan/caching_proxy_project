
from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class TestOriginHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = {
            "message": "Hello from test origin",
            "path": self.path,
        }

        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()

        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 9000), TestOriginHandler)

    print("Test origin running on http://127.0.0.1:9000")

    server.serve_forever()
