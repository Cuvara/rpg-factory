"""assetgen.py model-hashes: write the model sha256 cache that the local-stage manifest reads (hooked up by assetgen.py).

  model-hashes [--models-dir DIR | --comfy-dir DIR] [--desktop-dir DIR] [--instance NAME|ID] [--kind K]...
               [--extra-model-paths FILE]... [--no-extra-model-paths] [--json]

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

Extra model folders (ComfyUI's extra_model_paths.yaml): the files read, in this order and each once, follow ComfyUI's
main.py (apply_custom_paths), which loads <comfy root>/extra_model_paths.yaml first and then the files named on its command
line: unless --no-extra-model-paths (it turns off auto-discovery only), <comfy root>/extra_model_paths.yaml (the parent
directory of the models directory: headless ComfyUI keeps it next to main.py); then, on the Comfy Desktop route, <desktop
data dir>/instance-model-paths/<instance id>.yaml (Comfy Desktop writes it and passes it to ComfyUI on the command line;
it is auto-discovered, so it is read right after the root file and before the explicit files, and --no-extra-model-paths
skips it too); then every --extra-model-paths FILE in the order given (repeatable; a FILE that does not exist exits 2). A
missing auto-discovered file is skipped silently. The files are parsed with a stdlib reader of
the YAML subset ComfyUI and Comfy Desktop write (named sections; indented key: value lines; plain, 'single' and "double"
quoted scalars; | |- |+ block scalars; # comments; no flow collections, nesting, anchors or tabs). Folders resolve as
ComfyUI's load_extra_path_config does: base_path (expanduser, expandvars, relative to the file's directory), then per hashed
kind each non-empty line of the value joined to base_path, or, without one, relative to the file's directory; base_path and
is_default are not kinds. is_default follows Python truthiness of the value yaml.safe_load gives ComfyUI, mapped by the
subset reader without a YAML library: a plain true/True/TRUE/yes/Yes/YES/on/On/ON is true, a plain false/no/off (same
spellings), null/Null/NULL/~ or an empty value is false, a plain number is true unless it is zero (0, -0, 0.0, 0x0, 0b0, 00 ...,
the PyYAML YAML 1.1 forms), any other plain text is a non-empty string and so true; a quoted or block scalar is always a
string, so 'false', "no" and '0' are true (ComfyUI treats them as is_default) and only an empty quoted string is false. Per
kind the folders are walked in order: the extra folders of is_default sections in REVERSE
declaration order (ComfyUI inserts each is_default folder at index 0, so the last declared wins), the models folder as
before, then the other extra folders in declaration order; a folder named twice is walked once and a missing one is skipped. ComfyUI
loads the first match, so a row name found in a later folder is skipped with a warning (annotators keep the base name rule
across all folders). A malformed or unreadable file is a warning (the file is ignored, the exit code is not raised), never a
crash. Reuse by size and mtime_ns, the cache schema and the row fields are unchanged.

Hashing: sha256 over 1 MiB chunks, never a whole file in memory (models are several GB). A row is
{kind, name, sha256, size, mtime_ns}; an existing row of the same kind and name with an equal size and mtime_ns and a valid
sha256 is reused without reading the file. A file whose size or mtime changed while it was hashed is skipped with a warning
(exit 1). Schema stays rpg-factory.comfy-model-hashes/1: size and mtime_ns are optional additive row fields, models_dir
an additive top-level field, and the reader ignores all of them. Rows are sorted by kind and name; rows of kinds not scanned
this time are kept, rows of a scanned kind whose file is gone are dropped; a malformed existing cache counts as empty.

Output: one line per kind "<kind>: N files, H hashed, R reused", one line "extra model paths <file>: N folders" per extra
file read without error, and the written path; --json prints schema rpg-factory.assetgen-model-hashes/1 (indent 1, sorted
keys): path, models_dir, kinds {files, hashed, reused}, extra_model_paths [{path, folders {kind: [dir]}}], warnings, rows.
Exit codes: 0 written, 1 a file could not be read or changed while it was hashed (the readable rows are still written), 2
usage (no models directory, an unknown kind, a missing --extra-model-paths file).
"""
import hashlib
import json
import os
import re
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
    """(installPath/ComfyUI/models, None, instance id) of the instance pick_instance would choose; (None, reason, None)
    when there is none."""
    path = os.path.join(ddir, "installations.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, UnicodeError):
        data = None
    if not isinstance(data, list):
        return None, "no installations.json in the Comfy Desktop data dir %s" % ddir.replace(os.sep, "/"), None
    local = [i for i in data if isinstance(i, dict) and i.get("sourceId") != "cloud" and i.get("installPath")]
    if want:
        local = [i for i in local if want in (i.get("id"), i.get("name"))]
    if not local:
        return None, "no local Comfy Desktop instance%s in %s" % (" named %r" % want if want else "", path.replace(os.sep, "/")), None
    local.sort(key=lambda i: (i.get("sourceId") != "standalone",
                              -(i.get("lastLaunchedAt") if isinstance(i.get("lastLaunchedAt"), (int, float)) else 0)))
    return os.path.join(str(local[0]["installPath"]), "ComfyUI", "models"), None, local[0].get("id")


def resolve_source(models_dir, comfy_dir, desktop_dir, instance):
    """(models directory, None, desktop extra file or None), or (None, one-line reason naming what was tried, None). The
    desktop extra file is Comfy Desktop's instance-model-paths/<instance id>.yaml, only on the Comfy Desktop route."""
    desktop_file = None
    if models_dir:
        found, tried = models_dir, "--models-dir"
    elif comfy_dir:
        found, tried = os.path.join(comfy_dir, "models"), "--comfy-dir"
    else:
        ddir = _desktop_dir(desktop_dir)
        found, reason, inst = _desktop_models(ddir, instance)
        if found is None:
            return None, "%s; pass --models-dir DIR, --comfy-dir DIR or --desktop-dir DIR" % reason, None
        tried = "Comfy Desktop"
        if isinstance(inst, str) and inst and inst == os.path.basename(inst) and inst not in (".", ".."):
            desktop_file = os.path.join(ddir, "instance-model-paths", inst + ".yaml")
    if not os.path.isdir(found):
        return None, "the ComfyUI models directory %s (from %s) does not exist; pass --models-dir, --comfy-dir or --desktop-dir" % (
            found.replace(os.sep, "/"), tried), None
    return found, None, desktop_file


def resolve_models_dir(models_dir, comfy_dir, desktop_dir, instance):
    """(models directory, None), or (None, one-line reason naming what was tried)."""
    found, reason, _ = resolve_source(models_dir, comfy_dir, desktop_dir, instance)
    return found, reason


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


EXTRA_FILE = "extra_model_paths.yaml"
# PyYAML's YAML 1.1 resolver (yaml.safe_load, which ComfyUI's load_extra_path_config uses): the exact spellings of a plain
# bool and null, and the plain int / float forms. Anything else plain is a string.
YAML_TRUE = ("true", "True", "TRUE", "yes", "Yes", "YES", "on", "On", "ON")
YAML_FALSE = ("false", "False", "FALSE", "no", "No", "NO", "off", "Off", "OFF")
YAML_NULL = ("", "~", "null", "Null", "NULL")
YAML_NUMBER = re.compile(
    r"[-+]?0b[0-1_]+|[-+]?0[0-7_]+|[-+]?(?:0|[1-9][0-9_]*)|[-+]?0x[0-9a-fA-F_]+|[-+]?[1-9][0-9_]*(?::[0-5]?[0-9])+"
    r"|[-+]?[0-9][0-9_]*\.[0-9_]*(?:[eE][-+][0-9]+)?|\.[0-9_]+(?:[eE][-+][0-9]+)?|[-+]?[0-9][0-9_]*(?::[0-5]?[0-9])+\.[0-9_]*"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN)")


class Quoted(str):
    """A scalar the parser read quoted ('...' or "...") or as a | block: YAML makes it a string whatever its text, so
    'false' stays a non-empty (truthy) string. A plain scalar stays a bare str."""


def _number_is_zero(text):
    """True when a plain scalar that matched YAML_NUMBER has the value zero (so Python truthiness says false)."""
    t = text.replace("_", "").lstrip("+-")
    try:
        if ":" in t:
            return all(float(part) == 0 for part in t.split(":"))
        if t.startswith("0x"):
            return int(t[2:], 16) == 0
        if t.startswith("0b"):
            return int(t[2:], 2) == 0
        if re.fullmatch(r"0[0-7]+", t):
            return int(t, 8) == 0
        return float(t) == 0   # 0, 0.0, .0, 1e+5; .inf and .nan raise ValueError: truthy
    except ValueError:
        return False


def yaml_truthy(value):
    """Python truthiness of what yaml.safe_load would give ComfyUI for this scalar (the reader keeps Quoted apart): a quoted
    or block scalar is a string (empty is false); a plain one is a bool word, null, a number (zero is false) or a string."""
    if isinstance(value, Quoted):
        return bool(value)
    if value in YAML_TRUE:
        return True
    if value in YAML_FALSE or value in YAML_NULL:
        return False
    if YAML_NUMBER.fullmatch(value):
        return not _number_is_zero(value)
    return True


def _fail(reason):
    raise ValueError(reason)


def _quoted(text, start, lineno):
    """(value, index after the closing quote) of the 'single' or "double" quoted scalar that starts at text[start]."""
    quote, out, i = text[start], [], start + 1
    while i < len(text):
        c = text[i]
        if c == quote:
            if quote == "'" and text[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), i + 1
        if quote == '"' and c == "\\" and text[i + 1:i + 2] in ("\\", '"'):
            out.append(text[i + 1])
            i += 2
            continue
        out.append(c)
        i += 1
    _fail("line %d: unterminated %s quote" % (lineno, "single" if quote == "'" else "double"))


def _tail_ok(rest):
    """True when only blanks or a # comment follow a quoted scalar."""
    rest = rest.strip()
    return not rest or rest.startswith("#")


def _split_key(text, lineno):
    """(key, text after the colon) of a `key: rest` line; key plain, 'single' or "double" quoted."""
    if text[0] in "'\"":
        key, end = _quoted(text, 0, lineno)
        after = text[end:].lstrip(" ")
        if not after.startswith(":") or (after[1:2] not in ("", " ")):
            _fail("line %d: expected key: value" % lineno)
        return key, after[1:]
    if text[0] in "{[" or text[0] == "-" and text[1:2] in ("", " ") or text[0] in "&*!?%@`|>":
        _fail("line %d: unsupported YAML syntax (flow collection, list, anchor or tag)" % lineno)
    for i, c in enumerate(text):
        if c == ":" and text[i + 1:i + 2] in ("", " "):
            key = text[:i].strip()
            if not key or key.startswith("#"):
                break
            return key, text[i + 1:]
    _fail("line %d: expected key: value" % lineno)


def _scalar(rest, lineno):
    """The scalar value of what follows `key:` (a block scalar header is handled by the caller)."""
    rest = rest.strip()
    if not rest or rest.startswith("#"):
        return ""
    if rest[0] in "'\"":
        value, end = _quoted(rest, 0, lineno)
        if not _tail_ok(rest[end:]):
            _fail("line %d: unexpected text after the quoted value" % lineno)
        return Quoted(value)
    if rest[0] in "{[":
        _fail("line %d: flow collections are not supported" % lineno)
    if rest[0] in "&*!>@`":
        _fail("line %d: unsupported YAML syntax (anchor, alias, tag or folded scalar)" % lineno)
    cut = rest.find(" #")
    value = (rest if cut < 0 else rest[:cut]).strip()
    if ": " in value or value.endswith(":"):
        _fail("line %d: expected key: value" % lineno)
    return value


def parse_extra_paths(text):
    """[(section name, {key: value})] of an extra_model_paths.yaml, in file order (the subset in the module docstring);
    raises ValueError("line N: reason") on anything else. An empty section is dropped (ComfyUI skips a None conf)."""
    if "\0" in text:
        _fail("line 1: not a text file")
    lines = text.lstrip("﻿").splitlines()
    sections, current, key_indent, i = [], None, None, 0
    while i < len(lines):
        raw, lineno = lines[i], i + 1
        i += 1
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if raw[indent:indent + 1] == "\t":
            _fail("line %d: tab indentation is not supported" % lineno)
        if indent == 0:
            name, rest = _split_key(raw.rstrip(), lineno)
            if _scalar(rest, lineno) != "":
                _fail("line %d: a section name must be followed by an indented block" % lineno)
            current, key_indent = {}, None
            sections.append((name, current))
            continue
        if current is None:
            _fail("line %d: a key outside a section" % lineno)
        if key_indent is None:
            key_indent = indent
        elif indent != key_indent:
            _fail("line %d: nested mappings and mixed indentation are not supported" % lineno)
        key, rest = _split_key(body, lineno)
        head = rest.strip()
        if head.startswith("|"):
            header = head.split(" #")[0].strip()
            if header not in ("|", "|-", "|+"):
                _fail("line %d: unsupported block scalar header %s" % (lineno, header))
            block, block_indent = [], None
            while i < len(lines):
                nxt = lines[i]
                if nxt.strip():
                    deep = len(nxt) - len(nxt.lstrip(" "))
                    if deep <= key_indent:
                        break
                    if block_indent is None:
                        block_indent = deep
                    elif deep < block_indent:
                        _fail("line %d: block scalar indentation" % (i + 1))
                    block.append(nxt[block_indent:].rstrip())
                else:
                    block.append("")
                i += 1
            while block and not block[-1]:
                block.pop()
            value = Quoted("\n".join(block))
        else:
            value = _scalar(rest, lineno)
        current[key] = value
    return [(n, c) for n, c in sections if c]


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def read_extra_file(path, kinds):
    """([(kind, folder, is_default)] in file order, None), or (None, reason) for a file that cannot be read or parsed.
    Folders follow ComfyUI's utils/extra_config.py load_extra_path_config; only kinds in `kinds` are kept."""
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        return None, "not read (%s)" % (exc.strerror or exc)
    except UnicodeError:
        return None, "not read (not UTF-8 text)"
    try:
        sections = parse_extra_paths(text)
    except ValueError as exc:
        return None, str(exc)
    here = os.path.dirname(os.path.abspath(path))
    entries = []
    try:
        for _, conf in sections:
            base = conf.get("base_path")
            if base:
                base = os.path.expandvars(os.path.expanduser(base))
                if not os.path.isabs(base):
                    base = os.path.abspath(os.path.join(here, base))
            default = yaml_truthy(conf.get("is_default", ""))
            for key, value in conf.items():
                if key not in kinds:
                    continue
                for line in value.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    full = os.path.join(base, line) if base else (line if os.path.isabs(line) else os.path.join(here, line))
                    entries.append((key, os.path.normpath(full), default))
    except ValueError as exc:
        return None, "not read (%s)" % exc
    return entries, None


def extra_candidates(explicit, no_auto, models_dir, desktop_file):
    """The extra files to read, in ComfyUI's load order and each once: (unless no_auto) <comfy root>/extra_model_paths.yaml
    (main.py loads it first), the Comfy Desktop instance file (Desktop passes it on the command line; auto-discovered, so
    before the explicit ones), then the explicit files as given (the command line files). Only the auto-discovered ones may
    be missing (they are dropped here). A file named again later is not read again (its first position stands)."""
    found = []
    if not no_auto:
        for auto in (os.path.join(os.path.dirname(os.path.abspath(models_dir)), EXTRA_FILE), desktop_file):
            if auto and os.path.isfile(auto):
                found.append(auto)
    found += list(explicit)
    out, seen = [], set()
    for path in found:
        if _norm(path) not in seen:
            seen.add(_norm(path))
            out.append(path)
    return out


def load_extra(paths, kinds, warnings):
    """({kind: [(folder, is_default)]} over all files read without error, [report entries for the JSON and text output])."""
    folders, report = {}, []
    for path in paths:
        shown = os.path.abspath(path).replace(os.sep, "/")
        entries, reason = read_extra_file(path, kinds)
        if entries is None:
            warnings.append("extra model paths %s: %s; file ignored" % (shown, reason))
            continue
        per_kind = {}
        for kind, folder, default in entries:
            folders.setdefault(kind, []).append((folder, default))
            per_kind.setdefault(kind, []).append(folder.replace(os.sep, "/"))
        report.append({"path": shown, "folders": per_kind, "count": len(entries)})
    return folders, report


def kind_files(models_dir, kind, warnings, extra=()):
    """[(path, row name)] of one kind. annotators are named by base name (see the module docstring). extra is the
    [(folder, is_default)] of the extra model path files for this kind in declaration order: is_default folders come
    before the models folder in REVERSE declaration order (ComfyUI's add_model_folder_path inserts each is_default folder
    at index 0, so the last declared is searched first), the others after it in declaration order, and a folder given
    twice is walked once."""
    before = [f for f, d in extra if d][::-1]
    after = [f for f, d in extra if not d]
    if kind != "annotators":
        found, taken, walked = [], {}, set()
        for folder in before + [os.path.join(models_dir, kind)] + after:
            if _norm(folder) in walked or not os.path.isdir(folder):
                continue
            walked.add(_norm(folder))
            for path, name in _model_files(folder):
                if name in taken:
                    warnings.append("%s: %s in %s is shadowed by an earlier folder, skipped" % (
                        kind, name, folder.replace(os.sep, "/")))
                    continue
                taken[name] = folder
                found.append((path, name))
        return found
    found, walked = [], set()
    for folder in before + [os.path.join(os.path.dirname(os.path.abspath(models_dir)), ANNOTATOR_NODE_DIR),
                            os.path.join(models_dir, "annotators")] + after:
        if _norm(folder) not in walked and os.path.isdir(folder):
            walked.add(_norm(folder))
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


def scan(models_dir, kinds, old_rows, extra=None, warnings=None):
    """(rows of the scanned kinds, per-kind counts, warnings, number of unreadable files). extra is
    {kind: [(folder, is_default)]} from load_extra; warnings, when given, is the list to extend (and return)."""
    old = {(r["kind"], r["name"]): r for r in old_rows}
    rows, counts, errors = [], {}, 0
    warnings = [] if warnings is None else warnings
    extra = extra or {}
    for kind in kinds:
        count = counts[kind] = {"files": 0, "hashed": 0, "reused": 0}
        for path, name in kind_files(models_dir, kind, warnings, extra.get(kind, ())):
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
    models_dir, reason, desktop_file = resolve_source(a.models_dir, a.comfy_dir, a.desktop_dir, a.instance)
    if models_dir is None:
        ag.fail("model-hashes: " + reason, 2)
    explicit = list(getattr(a, "extra_model_paths", None) or [])
    for item in explicit:
        if not os.path.isfile(item):
            ag.fail("model-hashes --extra-model-paths %s: no such file" % item.replace(os.sep, "/"), 2)
    warnings = []
    extra, report = load_extra(extra_candidates(explicit, getattr(a, "no_extra_model_paths", False), models_dir, desktop_file),
                               kinds, warnings)
    path = os.path.abspath(cache_path())
    old = read_cache(path)
    rows, counts, warnings, errors = scan(models_dir, kinds, old, extra, warnings)
    kept = [r for r in old if r["kind"] not in kinds]
    all_rows = sorted(kept + rows, key=lambda r: (r["kind"], r["name"]))
    models_dir = os.path.abspath(models_dir).replace(os.sep, "/")
    fstate.write_json(path, {"schema": SCHEMA, "models_dir": models_dir, "models": all_rows}, indent=1)
    shown = path.replace(os.sep, "/")
    lines = ["%s: %d files, %d hashed, %d reused" % (k, c["files"], c["hashed"], c["reused"]) for k, c in counts.items()]
    lines += ["extra model paths %s: %d folders" % (r["path"], r["count"]) for r in report]
    lines.append("wrote %s (%d rows, models in %s)" % (shown, len(all_rows), models_dir))
    for w in warnings:
        print("assetgen: warning: " + w, file=sys.stderr)
    ag.emit({"schema": RESULT_SCHEMA, "path": shown, "models_dir": models_dir, "kinds": counts,
             "extra_model_paths": [{"path": r["path"], "folders": r["folders"]} for r in report],
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
    c.add_argument("--extra-model-paths", action="append", default=[], metavar="FILE", help="an extra_model_paths.yaml whose "
                   "model folders are hashed too (repeatable; read in the order given, after the auto-discovered "
                   "<comfy root>/extra_model_paths.yaml and Comfy Desktop instance-model-paths/<id>.yaml, the order "
                   "ComfyUI loads them; is_default follows Python truthiness, so a quoted 'false' is a default)")
    c.add_argument("--no-extra-model-paths", action="store_true", help="do not auto-discover extra_model_paths files "
                   "(explicit --extra-model-paths files are still read)")
    c.add_argument("--json", action="store_true")
    return c
