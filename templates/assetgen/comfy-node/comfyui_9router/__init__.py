"""NineRouterImage / NineRouterChat: ComfyUI nodes that call the user's 9router gateway.

Credentials are never stored here: base_url and Authorization are read at run time
from the Codex provider config ([model_providers.9router] in ~/.codex/config.toml;
override the file with NINEROUTER_CODEX_CONFIG, the provider with NINEROUTER_PROVIDER).
"""
import base64, io, json, os, tomllib, urllib.error, urllib.request, uuid
import numpy as np
import torch
from PIL import Image


def _provider():
    path = os.environ.get("NINEROUTER_CODEX_CONFIG") or os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
    name = os.environ.get("NINEROUTER_PROVIDER", "9router")
    with open(path, "rb") as f:
        p = tomllib.load(f)["model_providers"][name]
    return p["base_url"].rstrip("/"), p["http_headers"]["Authorization"]


def _post(path, body, content_type="application/json", timeout=600):
    base, auth = _provider()
    req = urllib.request.Request(base + path, data=body, method="POST",
                                 headers={"Authorization": auth, "Content-Type": content_type, "User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"9router {path} HTTP {e.code}: {e.read()[:500].decode('utf-8', 'replace')}") from None


def _tensor_to_png(t):
    a = (t.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    return buf.getvalue()


def _png_to_tensor(data):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    return torch.from_numpy(np.array(im).astype(np.float32) / 255.0)[None, ...]


def _multipart(fields, files):
    b = uuid.uuid4().hex
    out = io.BytesIO()
    for k, v in fields.items():
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    for k, name, data in files:
        out.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{name}"\r\nContent-Type: image/png\r\n\r\n'.encode())
        out.write(data + b"\r\n")
    out.write(f"--{b}--\r\n".encode())
    return out.getvalue(), f"multipart/form-data; boundary={b}"


class NineRouterImage:
    CATEGORY = "9router"
    FUNCTION = "run"
    RETURN_TYPES = ("IMAGE",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "user_prompt": ("STRING", {"multiline": True, "forceInput": True}),
            "model": ("STRING", {"default": "cx/gpt-5.6-sol-image"}),
            "size": (["auto", "1024x1024", "1536x1024", "1024x1536"],),
            "quality": (["auto", "low", "medium", "high"],),
            "background": (["auto", "opaque", "transparent"],),
        }, "optional": {"reference_images": ("IMAGE",)}}

    def run(self, user_prompt, model, size, quality, background, reference_images=None):
        fields = {"model": model, "prompt": user_prompt, "size": size, "quality": quality, "background": background, "n": 1}
        if reference_images is None:
            res = _post("/images/generations", json.dumps(fields).encode())
        else:
            files = [("image[]", f"ref{i}.png", _tensor_to_png(t)) for i, t in enumerate(reference_images)]
            body, ct = _multipart({k: str(v) for k, v in fields.items()}, files)
            res = _post("/images/edits", body, ct)
        item = res["data"][0]
        if "b64_json" in item and item["b64_json"]:
            data = base64.b64decode(item["b64_json"])
        else:
            with urllib.request.urlopen(item["url"], timeout=120) as r:
                data = r.read()
        return (_png_to_tensor(data),)


class NineRouterChat:
    CATEGORY = "9router"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING",)

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"user_prompt": ("STRING", {"multiline": True}),
                             "model": ("STRING", {"default": "cx/gpt-6-sol"}),
                             "system_prompt": ("STRING", {"multiline": True, "default": ""})}}

    def run(self, user_prompt, model, system_prompt):
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [{"role": "user", "content": user_prompt}]
        res = _post("/chat/completions", json.dumps({"model": model, "messages": msgs}).encode())
        return (res["choices"][0]["message"]["content"],)


NODE_CLASS_MAPPINGS = {"NineRouterImage": NineRouterImage, "NineRouterChat": NineRouterChat}
NODE_DISPLAY_NAME_MAPPINGS = {"NineRouterImage": "9Router Image", "NineRouterChat": "9Router Chat"}
