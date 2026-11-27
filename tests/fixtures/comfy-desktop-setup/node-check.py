"""Offline checks of the vendored 9router node (templates/assetgen/comfy-node/comfyui_9router/__init__.py).
Imports it with stub numpy/torch/PIL (the Desktop env has the real ones), compares its signature with
scripts/assetgen/data/known-nodes.json and exercises the run-time provider lookup against a loopback fake gateway.
Usage: node-check.py PLUGIN_ROOT TMPDIR. Prints one `ok ...` or `not ok ...` line per check."""
import importlib.util, json, os, sys, threading, types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

root, tmp = sys.argv[1:3]
for name in ("numpy", "torch", "PIL", "PIL.Image"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["PIL"].Image = sys.modules["PIL.Image"]
path = os.path.join(root, "templates/assetgen/comfy-node/comfyui_9router/__init__.py")
spec = importlib.util.spec_from_file_location("comfyui_9router", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
known = json.load(open(os.path.join(root, "scripts/assetgen/data/known-nodes.json")))["nodes"]
tpl = json.load(open(os.path.join(root, "templates/assetgen/workflows/image-generate.json")))


def check(label, cond):
    print(("ok " if cond else "not ok ") + label)


check("node classes are exactly NineRouterImage and NineRouterChat", sorted(mod.NODE_CLASS_MAPPINGS) == ["NineRouterChat", "NineRouterImage"])
for cname in ("NineRouterImage", "NineRouterChat"):
    cls, k = mod.NODE_CLASS_MAPPINGS[cname], known[cname]
    it = cls.INPUT_TYPES()
    got = [(n, v[0] if isinstance(v[0], str) else "COMBO", v[0] if isinstance(v[0], list) else None, True) for n, v in it["required"].items()]
    got += [(n, v[0], None, False) for n, v in it.get("optional", {}).items()]
    want = [(n, d["type"], d.get("options"), d["required"]) for n, d in k["inputs"].items()]
    check("%s inputs (names, order, types, options, required) equal known-nodes.json" % cname, got == want)
    check("%s outputs equal known-nodes.json" % cname, list(cls.RETURN_TYPES) == k["outputs"])
check("NineRouterImage default model equals the image-generate template default",
      mod.NineRouterImage.INPUT_TYPES()["required"]["model"][1]["default"] == tpl["params"]["model"]["default"])

seen = []


class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers["Content-Length"])
        seen.append((self.path, self.headers.get("Authorization"), self.rfile.read(n)))
        body = b'{"data": [{"b64_json": "AA=="}]}'
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
cfg = os.path.join(tmp, "node-codex.toml")
open(cfg, "w").write('[model_providers.testprov]\nbase_url = "http://127.0.0.1:%d/v1/"\nhttp_headers = { Authorization = "test-placeholder-not-a-key" }\n' % srv.server_address[1])
os.environ["NINEROUTER_CODEX_CONFIG"], os.environ["NINEROUTER_PROVIDER"] = cfg, "testprov"
res = mod._post("/images/generations", b'{"n": 1}')
check("the node reads base_url and Authorization from the Codex provider config at run time",
      res["data"][0]["b64_json"] == "AA==" and seen[0][0] == "/v1/images/generations" and seen[0][1] == "test-placeholder-not-a-key")
os.environ["NINEROUTER_PROVIDER"] = "absent"
try:
    mod._post("/x", b"{}")
    check("a missing provider section raises", False)
except KeyError:
    check("a missing provider section raises (nothing is sent)", len(seen) == 1)
src = open(path).read()
check("the node source holds no URL scheme, IP address or key value",
      "://" not in src and "sk-" not in src and "Bearer" not in src)
