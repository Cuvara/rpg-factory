"""assetgen.py model-hashes: write the model sha256 cache that the local-stage manifest reads (hooked up by assetgen.py).

  model-hashes [--models-dir DIR | --comfy-dir DIR] [--desktop-dir DIR] [--instance NAME|ID] [--kind K]... [--json]

Hashes the local ComfyUI model files of the kinds asset-gen records and writes the cache file `assetgen.py manifest`
reads (assetgen.model_hashes): <persistent state dir>/comfy/model-hashes.json, or ASSETGEN_MODEL_HASHES when set. It
writes Factory state only (through fstate.write_json, atomic): never $TMPDIR directly, never a product repo, never the
ComfyUI install; the model files are only read.

Models directory, first match wins (the same rules as scripts/comfy-desktop-setup.py):
  --models-dir DIR     the ComfyUI models directory itself
  --comfy-dir DIR      a headless ComfyUI root (main.py): DIR/models
  Comfy Desktop        data dir = --desktop-dir, else COMFY_DESKTOP_DIR, else the per-OS default (desktop_dir); the local
                       instance is chosen as pick_instance does (no sourceId cloud, an installPath; --instance filters by id
                       or name; standalone first, then the latest lastLaunchedAt); its models directory is
                       installPath/ComfyUI/models (asset_rows). Those few lines are replicated here because that script's
                       file name is not importable.
When nothing resolves or the directory is missing: exit 2 with a one-line message, nothing is written.

Kinds: by default the model kinds of runfiles.MODEL_LOADERS (checkpoints, loras, controlnet, upscale_models, annotators;
the preset kind of PRESET_LOADERS is not a file), --kind (repeatable) limits to those, an unknown kind exits 2. A kind
is the folder models/<kind>/, walked recursively for .safetensors .ckpt .pt .pth .bin .gguf .onnx files; a row name is
the path below that folder with "/" separators (the lookup in model_hashes and runfiles.local_generation folds "\\" to
"/" too, ComfyUI on Windows names subfolder models with it). annotators: the controlnet_aux node keeps its models under
ComfyUI/custom_nodes/comfyui_controlnet_aux/ckpts/<repo>/ and workflows name them by file name, so that folder (and
models/annotators when present) is walked and the row name is the base name; a base name found twice is skipped with a
warning.

Hashing: sha256 over 1 MiB chunks, never a whole file in memory (models are several GB). A row is
{kind, name, sha256, size, mtime_ns}; an existing row of the same kind and name with an equal size and mtime_ns and a valid
sha256 is reused without reading the file. A file whose size or mtime changed while it was hashed is skipped with a warning
(exit 1). Schema stays rpg-factory.comfy-model-hashes/1: size and mtime_ns are optional additive row fields, models_dir
an additive top-level field, and the reader ignores all of them. Rows are sorted by kind and name; rows of kinds not scanned
this time are kept, rows of a scanned kind whose file is gone are dropped; a malformed existing cache counts as empty.

Output: one line per kind "<kind>: N files, H hashed, R reused" and the written path; --json prints schema
rpg-factory.assetgen-model-hashes/1 (indent 1, sorted keys): path, models_dir, kinds {files, hashed, reused}, warnings, rows.
Exit codes: 0 written, 1 a file could not be read or changed while it was hashed (the readable rows are still written), 2
usage (no models directory, an unknown kind).
"""
import hashlib
import json
import os
import sys

import fstate
import runfiles

SCHEMA = "rpg-factory.comfy-model-hashes/1"
RESULT_SCHEMA = "rpg-factory.assetgen-model-hashes/1"
CHUNK = 1 << 20
EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx")
ANNOTATOR_NODE_DIR = os.path.join("custom_nodes", "comfyui_controlnet_aux", "ckpts")


def default_kinds():
    """The model kinds of runfiles.MODEL_LOADERS in declaration order, each once (never a second hard-coded list)."""
    kinds = []
    for _, kind in runfiles.MODEL_LOADERS.values():
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def cache_path():
    return os.environ.get("ASSETGEN_MODEL_HASHES") or os.path.join(fstate.persistent(), "comfy", "model-hashes.json")


def _desktop_dir(arg):
    """scripts/comfy-desktop-setup.py desktop_dir."""
    if arg:
        return arg
    if os.environ.get("COMFY_DESKTOP_DIR"):
        return os.environ["COMFY_DESKTOP_DIR"]
    home = os.path.expanduser("~")
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"), "Comfy Desktop")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "Comfy Desktop")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"), "Comfy Desktop")


def _desktop_models(ddir, want):
    """installPath/ComfyUI/models of the instance pick_instance would choose; (None, reason) when there is none."""
    path = os.path.join(ddir, "installations.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeError):
        data = None
    if not isinstance(data, list):
        return None, "no installations.json in the Comfy Desktop data dir %s" % ddir.replace(os.sep, "/")
    local = [i for i in data if isinstance(i, dict) and i.get("sourceId") != "cloud" and i.get("installPath")]
    if want:
        local = [i for i in local if want in (i.get("id"), i.get("name"))]
    if not local:
        return None, "no local Comfy Desktop instance%s in %s" % (" named %r" % want if want else "", path.replace(os.sep, "/"))
    local.sort(key=lambda i: (i.get("sourceId") != "standalone",
                              -(i.get("lastLaunchedAt") if isinstance(i.get("lastLaunchedAt"), (int, float)) else 0)))
    return os.path.join(str(local[0]["installPath"]), "ComfyUI", "models"), None


def resolve_models_dir(models_dir, comfy_dir, desktop_dir, instance):
    """(models directory, None), or (None, one-line reason naming what was tried)."""
    if models_dir:
        found, tried = models_dir, "--models-dir"
    elif comfy_dir:
        found, tried = os.path.join(comfy_dir, "models"), "--comfy-dir"
    else:
        found, reason = _desktop_models(_desktop_dir(desktop_dir), instance)
        if found is None:
            return None, "%s; pass --models-dir DIR, --comfy-dir DIR or --desktop-dir DIR" % reason
        tried = "Comfy Desktop"
    if not os.path.isdir(found):
        return None, "the ComfyUI models directory %s (from %s) does not exist; pass --models-dir, --comfy-dir or --desktop-dir" % (
            found.replace(os.sep, "/"), tried)
    return found, None


def _model_files(directory):
    """(path, path below directory with '/') of every model file below directory, sorted."""
    out = []
    for root, dirs, names in os.walk(directory):
        dirs.sort()
        for name in sorted(names):
            if name.lower().endswith(EXTENSIONS):
                path = os.path.join(root, name)
                out.append((path, os.path.relpath(path, directory).replace(os.sep, "/")))
    return out


def kind_files(models_dir, kind, warnings):
    """[(path, row name)] of one kind. annotators are named by base name (see the module docstring)."""
    if kind != "annotators":
        folder = os.path.join(models_dir, kind)
        return _model_files(folder) if os.path.isdir(folder) else []
    found = []
    for folder in (os.path.join(os.path.dirname(os.path.abspath(models_dir)), ANNOTATOR_NODE_DIR),
                   os.path.join(models_dir, "annotators")):
        if os.path.isdir(folder):
            found += [(p, os.path.basename(p)) for p, _ in _model_files(folder)]
    count = {}
    for _, name in found:
        count[name] = count.get(name, 0) + 1
    for name in sorted(n for n, c in count.items() if c > 1):
        warnings.append("annotators: base name %s occurs %d times, skipped (a workflow names it by base name only)" % (name, count[name]))
    return [(p, n) for p, n in found if count[n] == 1]


def file_sha256(path):
    """sha256 over 1 MiB chunks; never reads the whole file at once."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def _valid(row):
    return (isinstance(row, dict) and isinstance(row.get("kind"), str) and isinstance(row.get("name"), str)
            and isinstance(row.get("sha256"), str) and runfiles.SHA256.fullmatch(row["sha256"]) is not None)


def read_cache(path):
    """The usable rows of an existing cache; a missing, malformed or foreign-schema file is empty."""
    cache = fstate.read_json(path, None)
    if not isinstance(cache, dict) or cache.get("schema") != SCHEMA or not isinstance(cache.get("models"), list):
        return []
    return [row for row in cache["models"] if _valid(row)]


def _int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def scan(models_dir, kinds, old_rows):
    """(rows of the scanned kinds, per-kind counts, warnings, number of unreadable files)."""
    old = {(r["kind"], r["name"]): r for r in old_rows}
    rows, counts, warnings, errors = [], {}, [], 0
    for kind in kinds:
        count = counts[kind] = {"files": 0, "hashed": 0, "reused": 0}
        for path, name in kind_files(models_dir, kind, warnings):
            count["files"] += 1
            try:
                before = os.stat(path)
                prior = old.get((kind, name))
                if prior is not None and prior.get("size") == before.st_size and prior.get("mtime_ns") == before.st_mtime_ns \
                        and _int(prior.get("size")) and _int(prior.get("mtime_ns")):
                    sha, mode = prior["sha256"], "reused"
                else:
                    sha, mode = file_sha256(path), "hashed"
                after = os.stat(path)
            except OSError as exc:
                warnings.append("%s/%s: not read (%s)" % (kind, name, exc.strerror or exc))
                errors += 1
                count["files"] -= 1
                continue
            if (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns):
                warnings.append("%s/%s: changed while it was hashed, skipped" % (kind, name))
                errors += 1
                count["files"] -= 1
                continue
            count[mode] += 1
            rows.append({"kind": kind, "name": name, "sha256": sha, "size": before.st_size, "mtime_ns": before.st_mtime_ns})
    return rows, counts, warnings, errors


def run(ag, a):
    """The model-hashes verb: returns the exit code (usage errors exit 2 through ag.fail)."""
    known = default_kinds()
    kinds = []
    for kind in a.kind or known:
        if kind not in known:
            ag.fail("model-hashes --kind %s: one of %s" % (kind, ", ".join(known)), 2)
        if kind not in kinds:
            kinds.append(kind)
    models_dir, reason = resolve_models_dir(a.models_dir, a.comfy_dir, a.desktop_dir, a.instance)
    if models_dir is None:
        ag.fail("model-hashes: " + reason, 2)
    path = os.path.abspath(cache_path())
    old = read_cache(path)
    rows, counts, warnings, errors = scan(models_dir, kinds, old)
    kept = [r for r in old if r["kind"] not in kinds]
    all_rows = sorted(kept + rows, key=lambda r: (r["kind"], r["name"]))
    models_dir = os.path.abspath(models_dir).replace(os.sep, "/")
    fstate.write_json(path, {"schema": SCHEMA, "models_dir": models_dir, "models": all_rows}, indent=1)
    shown = path.replace(os.sep, "/")
    lines = ["%s: %d files, %d hashed, %d reused" % (k, c["files"], c["hashed"], c["reused"]) for k, c in counts.items()]
    lines.append("wrote %s (%d rows, models in %s)" % (shown, len(all_rows), models_dir))
    for w in warnings:
        print("assetgen: warning: " + w, file=sys.stderr)
    ag.emit({"schema": RESULT_SCHEMA, "path": shown, "models_dir": models_dir, "kinds": counts,
             "warnings": warnings, "rows": all_rows}, a.json, "\n".join(lines))
    return 1 if errors else 0


def add_parser(subs):
    c = subs("model-hashes")
    group = c.add_mutually_exclusive_group()
    group.add_argument("--models-dir", metavar="DIR", help="the ComfyUI models directory itself")
    group.add_argument("--comfy-dir", metavar="DIR", help="a headless ComfyUI root (models are DIR/models)")
    c.add_argument("--desktop-dir", metavar="DIR", help="Comfy Desktop data dir (installations.json; default COMFY_DESKTOP_DIR, "
                   "else the per-OS default)")
    c.add_argument("--instance", metavar="NAME|ID", help="the Comfy Desktop local instance (default: standalone first, then the "
                   "latest launched)")
    c.add_argument("--kind", action="append", default=[], metavar="K", help="limit to this model kind (repeatable; default: "
                   + ", ".join(default_kinds()) + ")")
    c.add_argument("--json", action="store_true")
    return c
