"""Fake ComfyUI for tests/comfy-desktop-setup.test.sh: loopback only. Usage: fake-comfy.py PORT_FILE MODE_FILE LOG_FILE.
MODE_FILE holds `node` (NineRouterImage is in /object_info) or `nonode`; every request is appended to LOG_FILE as JSON."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port_file, mode_file, log_file = sys.argv[1:4]
PNG = b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + (8).to_bytes(4, "big") + (6).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00"


def mode():
    return open(mode_file).read().strip()


class H(BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log(self, body=None):
        with open(log_file, "a") as f:
            f.write(json.dumps({"method": self.command, "path": self.path, "body": body}) + "\n")

    def do_GET(self):
        self.log()
        if self.path == "/system_stats":
            return self.reply(200, b'{"system": {}}')
        if self.path == "/object_info/NineRouterImage":
            return self.reply(200, b'{"NineRouterImage": {}}' if mode() == "node" else b"{}")
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            return self.reply(200, json.dumps({pid: {"status": {"completed": True, "status_str": "success", "messages": []},
                                                      "outputs": {"3": {"images": [{"filename": "setup-test_00001_.png", "subfolder": "assetgen", "type": "output"}]}}}}).encode())
        if self.path.startswith("/view?"):
            return self.reply(200, PNG, "image/png")
        self.reply(404, b"{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        self.log(body)
        if self.path == "/prompt":
            return self.reply(200, b'{"prompt_id": "p1"}')
        self.reply(404, b"{}")

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
open(port_file, "w").write(str(srv.server_address[1]))
srv.serve_forever()
