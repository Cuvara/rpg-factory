#!/usr/bin/env python3
"""Read-only component catalog of com.cuvara.uitoolkit at a git ref, plus Unity's built-in controls.

Usage: ui_catalog.py [--uitoolkit DIR] [--ref REF] [--project DIR] [--kind KIND]... [--json]

Reads the UIToolkit git repository at a ref (git ls-tree / git cat-file, never the working tree):
public types in Runtime/** ([UxmlElement] elements with their [UxmlAttribute]s, services, presenter and
view bases, adapters), USS class constants (`*UssClassName`), `--cuvara-*` tokens from
Runtime/Theme/Resources/CuvaraTheme.uss, Editor menu items and public Editor types, Tools~ scripts,
and Samples~ (each sample and its UXML). Unity built-ins come from data/unity-builtins.json.

Repository: --uitoolkit, else registry repo `uitoolkit` under the workspace (RPG_FACTORY_WORKSPACE or
the discovered workspace). Ref: --ref (source "arg"), else the client pin `#vX.Y.Z` of
com.cuvara.uitoolkit in <project or workspace client>/Packages/manifest.json ("client-pin"), else the
highest v* tag ("latest-tag"). A client pin older than the ref used is reported (pin-bump follow-up).

Every entry: {id, kind, name, namespace, source: "<path>:<line>@<ref>" | docs URL, purpose, config,
requires, related_skills}. Kinds: package-type, package-uxml-element, package-service, theme-token,
uss-class, editor-tool, sample, unity-builtin.
No repository or an unknown ref: status NOT_AVAILABLE with the reason (built-ins only, nothing invented).
Exit 0 = PASS, 1 = NOT_AVAILABLE, 2 = usage. Writes nothing.
"""
import html
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(HERE, "data")
sys.path.append(os.path.join(PLUGIN_ROOT, "scripts", "lib"))

SCHEMA = "rpg-factory.ui-catalog/1"
PIN_RE = re.compile(r"#(v\d+\.\d+\.\d+[\w.-]*)$")
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
TYPE_RE = re.compile(r"^\s*public\s+((?:(?:sealed|abstract|static|partial|readonly)\s+)*)(class|interface|struct|enum)\s+(\w+)(<[^>{]*>)?")
NS_RE = re.compile(r"^\s*namespace\s+([\w.]+)")
MEMBER_RE = re.compile(r"^\s+public\s+(?:(?:static|async|override|virtual|abstract|readonly|sealed|new|event|const)\s+)*"
                       r"(?:[\w.<>\[\],?]+(?:\s*<[^>]*>)?\s+)?(\w+)\s*(?:<[^>]*>)?\s*[({;=]")
UXML_ATTR_RE = re.compile(r"\[UxmlAttribute(?:\(\s*\"([^\"]+)\"\s*\))?\]\s*public\s+([\w.<>\[\]?]+)\s+(\w+)")
USS_CONST_RE = re.compile(r"const\s+string\s+(\w*UssClassName)\s*=\s*\"([^\"]+)\"")
TOKEN_RE = re.compile(r"^\s*(--cuvara-[\w-]+)\s*:\s*([^;]+);")
MENU_RE = re.compile(r"\[MenuItem\(\s*(?:\"([^\"]+)\"|(\w+))")
SERVICE_TYPES = {"ConfirmDialog", "ToastService", "ScreenNavigator", "IScreenNavigator", "CuvaraThemeService",
                 "ICuvaraThemeService", "BackNavigationSource", "LoadingProgressTracker", "SettingsModel",
                 "FadeTransition", "SlideTransition", "UIToolkitListAdapter", "UIToolkitGridAdapter",
                 "UIToolkitMultiTemplateListAdapter", "ScreenRegistry", "UIToolkitViewFactory", "RootUIDocument"}
RELATED = [("Editor/Figma/", ["ui-figma-import"]), ("Editor/FigmaCore/", ["ui-figma-import", "ui-validation"]),
           ("Tools~/Figma", ["ui-figma-import"]), ("Tools~/UxmlCodegenCli/", ["ui-figma-import", "ui-validation"]),
           ("Samples~/FigmaImport/", ["ui-figma-import", "ui-toolkit-screen"]), ("Editor/", ["ui-toolkit-screen"]),
           ("Runtime/Theme/", ["ui-toolkit-screen", "ui-validation"]), ("Runtime/TestSupport/", ["ui-validation"]),
           ("Runtime/", ["ui-toolkit-screen"]), ("Samples~/", ["ui-toolkit-screen"])]


class Unavailable(Exception):
    pass


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout


def registry():
    return json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))


def workspace(reg):
    """The RPG MMO workspace. An explicit RPG_FACTORY_WORKSPACE is authoritative: if it lacks the markers there is
    no workspace (no fallback to the cwd or the default root), so a test or a user pointing it elsewhere never
    picks up a real workspace on the host."""
    env = os.environ.get(reg["workspace"]["root_env"])
    if env:
        ok = all(os.path.exists(os.path.join(env, m)) for m in reg["workspace"]["root_markers"])
        return os.path.abspath(env) if ok else None
    try:
        import context
        return context.find_workspace(reg)
    except Exception:  # no workspace is an answer, not a crash
        return None


def version_key(tag):
    m = TAG_RE.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def client_pin(project):
    """(ref, manifest path) of com.cuvara.uitoolkit in <project>/Packages/manifest.json, or (None, path|None)."""
    if not project:
        return None, None
    path = os.path.join(project, "Packages", "manifest.json")
    try:
        deps = json.load(open(path, encoding="utf-8")).get("dependencies", {})
    except (OSError, ValueError):
        return None, None
    m = PIN_RE.search(str(deps.get("com.cuvara.uitoolkit", "")))
    return (m.group(1) if m else None), path


def locate(uitoolkit=None, project=None):
    """(repo dir | None, client project | None, reason)."""
    reg = registry()
    ws = workspace(reg)
    if not project and ws:
        cand = os.path.join(ws, reg["repos"]["client"]["path"])
        project = cand if os.path.isdir(cand) else None
    if uitoolkit:
        repo = uitoolkit
    elif ws:
        repo = os.path.join(ws, reg["repos"]["uitoolkit"]["path"])
    else:
        return None, project, "no RPG MMO workspace found (set RPG_FACTORY_WORKSPACE or pass --uitoolkit)"
    if git(repo, "rev-parse", "--git-dir")[0] != 0:
        return None, project, f"no UIToolkit git repository at {repo}"
    return repo, project, ""


def resolve_ref(repo, ref=None, project=None):
    """{ref, source, commit, client_pin, warnings}; raises Unavailable."""
    pin, manifest = client_pin(project)
    tags = [t for t in git(repo, "tag", "--list", "v*")[1].split() if version_key(t)]
    latest = max(tags, key=version_key) if tags else None
    if ref:
        source = "arg"
    elif pin:
        ref, source = pin, "client-pin"
    elif latest:
        ref, source = latest, "latest-tag"
    else:
        raise Unavailable(f"no --ref, no client pin and no v* tag in {repo}")
    rc, sha = git(repo, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if rc != 0:
        raise Unavailable(f"ref {ref} ({source}) does not exist in {repo}")
    warnings = []
    if pin and version_key(pin) and version_key(ref) and version_key(pin) < version_key(ref):
        warnings.append(f"the client pins com.cuvara.uitoolkit {pin}, older than {ref}: entries absent at {pin} "
                        f"need a pin-bump follow-up before client code can use them")
    if source == "client-pin" and latest and version_key(latest) > version_key(pin):
        warnings.append(f"catalog read at the client pin {pin}; the newest tag is {latest}")
    return {"ref": ref, "source": source, "commit": sha.strip(), "client_pin": pin,
            "client_manifest": manifest, "latest_tag": latest, "warnings": warnings}


def read_blobs(repo, ref, paths):
    """{path: text} for every path at ref, through one git cat-file --batch."""
    if not paths:
        return {}
    req = "".join(f"{ref}:{p}\n" for p in paths).encode("utf-8")
    out = subprocess.run(["git", "-C", repo, "cat-file", "--batch"], input=req, capture_output=True).stdout
    res, i = {}, 0
    for p in paths:
        nl = out.index(b"\n", i)
        head = out[i:nl].split()
        if len(head) == 3 and head[1] == b"blob":
            size = int(head[2])
            res[p] = out[nl + 1:nl + 1 + size].decode("utf-8", errors="replace")
            i = nl + 1 + size + 1
        else:
            i = nl + 1
    return res


def related(path):
    for prefix, skills in RELATED:
        if path.startswith(prefix):
            return ["ui-component-selection"] + [s for s in skills if s != "ui-component-selection"]
    return ["ui-component-selection"]


def clean_doc(lines):
    text = " ".join(l.strip().lstrip("/").strip() for l in lines)
    m = re.search(r"<summary>(.*?)</summary>", text, re.S)
    text = m.group(1) if m else text
    text = re.sub(r"<see\s+(?:cref|langword)=\"([^\"]+)\"\s*/>", lambda x: x.group(1).split(".")[-1], text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:240]


def doc_before(lines, idx):
    """XML doc comment above line idx (0-based), skipping attributes."""
    j, doc = idx - 1, []
    while j >= 0 and lines[j].strip().startswith("["):
        j -= 1
    while j >= 0 and lines[j].strip().startswith("///"):
        doc.insert(0, lines[j])
        j -= 1
    return clean_doc(doc)


def kebab(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def asmdef_for(path, asmdefs):
    best = None
    for a, info in asmdefs.items():
        d = os.path.dirname(a) + "/"
        if path.startswith(d) and (best is None or len(d) > len(os.path.dirname(best)) + 1):
            best = a
    if not best:
        return []
    info = asmdefs[best]
    req = [f"asmdef {info.get('name', os.path.basename(best))}"]
    req += [f"package {v['name']}" + (f" {v['expression']}" if v.get("expression") else "")
            for v in info.get("versionDefines", []) if v.get("name")]
    return req


def scan_cs(path, text, ref, asmdefs, editor):
    out = []
    lines = text.splitlines()
    ns = next((m.group(1) for m in map(NS_RE.match, lines) if m), "")
    decls = [(i, m) for i, m in ((i, TYPE_RE.match(l)) for i, l in enumerate(lines)) if m]
    consts = dict(re.findall(r"const\s+string\s+(\w+)\s*=\s*\"([^\"]+)\"", text))
    for n, (i, m) in enumerate(decls):
        name, generic = m.group(3), (m.group(4) or "").replace(" ", "")
        if "X_NAME" in name:  # ScreenCreator template text, not a type
            continue
        end = decls[n + 1][0] if n + 1 < len(decls) else len(lines)
        body = lines[i + 1:end]
        uxml = any("[UxmlElement" in lines[k] for k in range(max(0, i - 3), i))
        if uxml:
            kind = "package-uxml-element"
            config = []
            for a in UXML_ATTR_RE.finditer("\n".join(body)):
                config.append(f"{a.group(1) or kebab(a.group(3))} ({a.group(2)})")
        else:
            members = []
            for l in body:
                mm = MEMBER_RE.match(l)
                if mm and mm.group(1) not in members and mm.group(1) != "class":
                    members.append("ctor" if mm.group(1) == name else mm.group(1))
            config = members[:24]
            kind = "editor-tool" if editor else ("package-service" if name in SERVICE_TYPES else "package-type")
        out.append({"id": f"{'editor' if editor else 'pkg'}:{name}{generic}", "kind": kind, "name": name + generic,
                    "namespace": ns, "source": f"{path}:{i + 1}@{ref}", "purpose": doc_before(lines, i),
                    "config": config, "requires": asmdef_for(path, asmdefs), "related_skills": related(path)})
    for k, l in enumerate(lines):
        for c in USS_CONST_RE.finditer(l):
            out.append({"id": f"uss:{c.group(2)}", "kind": "uss-class", "name": c.group(2), "namespace": ns,
                        "source": f"{path}:{k + 1}@{ref}", "purpose": doc_before(lines, k) or c.group(1),
                        "config": [c.group(1)], "requires": asmdef_for(path, asmdefs), "related_skills": related(path)})
        mi = MENU_RE.search(l)
        if mi and "isValidateFunction" not in l:
            menu = mi.group(1) or consts.get(mi.group(2) or "", "")
            if menu:
                cls = next((d[1].group(3) for d in reversed(decls) if d[0] < k), "")
                if not cls:
                    cm = [re.search(r"class\s+(\w+)", x) for x in lines[:k]]
                    cls = next((c.group(1) for c in reversed(cm) if c), "")
                cdoc = next((doc_before(lines, j) for j in range(k, -1, -1) if re.search(r"\bclass\s+" + re.escape(cls) + r"\b", lines[j])), "") if cls else ""
                out.append({"id": f"editor:{menu}", "kind": "editor-tool", "name": menu, "namespace": ns,
                            "source": f"{path}:{k + 1}@{ref}",
                            "purpose": (f"Unity menu item ({cls}). " + cdoc).strip()[:240], "config": [],
                            "requires": asmdef_for(path, asmdefs), "related_skills": related(path)})
    return out


def scan_uss_tokens(path, text, ref):
    out = []
    for k, l in enumerate(text.splitlines()):
        m = TOKEN_RE.match(l)
        if m:
            out.append({"id": f"token:{m.group(1)}", "kind": "theme-token", "name": m.group(1), "namespace": "",
                        "source": f"{path}:{k + 1}@{ref}", "purpose": "Cuvara theme variable (override it, not the component rules)",
                        "config": [f"default {m.group(2).strip()}"], "requires": [], "related_skills": related(path)})
    return out


def scan_tool(path, text, ref):
    if path.endswith(".py"):
        m = re.search(r'"""(.*?)(?:\n\n|""")', text, re.S)
        purpose = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    else:
        purpose = next((clean_doc(text.splitlines()[i:i + 8]) for i, l in enumerate(text.splitlines()) if "<summary>" in l), "")
    name = path.split("/")[1] if path.endswith(".cs") else os.path.basename(path)
    return {"id": f"editor:{name}", "kind": "editor-tool", "name": name, "namespace": "", "source": f"{path}:1@{ref}",
            "purpose": purpose[:240], "config": [], "requires": [], "related_skills": related(path)}


def builtins():
    return json.load(open(os.path.join(DATA, "unity-builtins.json"), encoding="utf-8"))["entries"]


def build(uitoolkit=None, ref=None, project=None):
    """The catalog dict. Never raises for a missing repo or ref: status NOT_AVAILABLE."""
    repo, project, reason = locate(uitoolkit, project)
    cat = {"schema": SCHEMA, "status": "PASS", "reason": "", "uitoolkit": None, "counts": {}, "entries": []}
    if repo:
        try:
            cat["uitoolkit"] = {"repo": repo, **resolve_ref(repo, ref, project)}
        except Unavailable as e:
            reason = str(e)
    if not cat["uitoolkit"]:
        cat.update(status="NOT_AVAILABLE", reason=reason, entries=builtins())
        cat["counts"] = {"unity-builtin": len(cat["entries"])}
        return cat
    r = cat["uitoolkit"]["ref"]
    files = git(repo, "ls-tree", "-r", "--name-only", r)[1].splitlines()
    wanted = [f for f in files if (f.endswith((".cs", ".asmdef")) and f.startswith(("Runtime/", "Editor/")))
              or f.startswith("Runtime/Theme/Resources/") and f.endswith(".uss")
              or f.startswith("Tools~/") and (f.endswith("Program.cs") or f.endswith(".py") and not os.path.basename(f).startswith("test_") and "/template/" not in f and os.path.basename(f) != "cli_smoke.py")
              or f.startswith("Samples~/") and f.endswith("/README.md") and f.count("/") == 2]
    blobs = read_blobs(repo, r, wanted)
    asmdefs = {}
    for f in wanted:
        if f.endswith(".asmdef"):
            try:
                asmdefs[f] = json.loads(blobs.get(f, "{}"))
            except ValueError:
                asmdefs[f] = {}
    entries = []
    for f in wanted:
        text = blobs.get(f)
        if text is None:
            continue
        if f.startswith("Tools~/"):
            entries.append(scan_tool(f, text, r))
        elif f.endswith(".cs"):
            entries += scan_cs(f, text, r, asmdefs, f.startswith("Editor/"))
        elif f.endswith(".uss"):
            entries += scan_uss_tokens(f, text, r)
        elif f.endswith("README.md"):
            sample = f.split("/")[1]
            para = next((p for p in re.split(r"\n\s*\n", text) if p.strip() and not p.lstrip().startswith("#")), "")
            uxml = [x for x in files if x.startswith(f"Samples~/{sample}/") and x.endswith(".uxml")]
            entries.append({"id": f"sample:{sample}", "kind": "sample", "name": sample, "namespace": "",
                            "source": f"{f}:1@{r}", "purpose": re.sub(r"\s+", " ", para).strip()[:240],
                            "config": [x.split("/", 2)[2] for x in uxml], "requires": [], "related_skills": related(f)})
            for x in uxml:
                entries.append({"id": f"sample:{x.split('/', 1)[1]}", "kind": "sample", "name": os.path.basename(x),
                                "namespace": "", "source": f"{x}:1@{r}", "purpose": f"UXML in the {sample} sample",
                                "config": [], "requires": [], "related_skills": related(x)})
    seen, unique = set(), []
    for e in entries + builtins():
        if e["id"] not in seen:
            seen.add(e["id"])
            unique.append(e)
    cat["entries"] = unique
    for e in unique:
        cat["counts"][e["kind"]] = cat["counts"].get(e["kind"], 0) + 1
    return cat


def find(cat, ref_id):
    """Catalog entries for a choice id: exact id, or every generic arity of pkg:/editor:<Name>."""
    return [e for e in cat["entries"] if e["id"] == ref_id or e["id"].startswith(ref_id + "<")]


def markdown(cat, kinds=None):
    out = ["## com.cuvara.uitoolkit component catalog", ""]
    u = cat.get("uitoolkit")
    if cat["status"] != "PASS":
        out += [f"**NOT_AVAILABLE**: {cat['reason']}. Only Unity built-ins are listed; no package entry is invented.", ""]
    else:
        out.append(f"Ref `{u['ref']}` ({u['source']}, commit {u['commit'][:10]}) from `{u['repo']}`; client pin: {u['client_pin'] or 'none'}.")
        out += [f"- warning: {w}" for w in u["warnings"]]
        out.append("")
    out.append("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(cat["counts"].items())))
    out += ["", "| id | kind | source | purpose |", "|---|---|---|---|"]
    for e in cat["entries"]:
        if kinds and e["kind"] not in kinds:
            continue
        out.append(f"| `{e['id']}` | {e['kind']} | {e['source']} | {e['purpose'][:100].replace('|', '/')} |")
    return "\n".join(out)


def parse(argv, extra=(), multi=("kind", "need")):
    """(options, other words). extra: (flag, key) pairs; keys in multi collect every value."""
    flags = {"--uitoolkit": "uitoolkit", "--ref": "ref", "--project": "project", "--kind": "kind", **dict(extra)}
    a = {k: ([] if k in multi else None) for k in flags.values()}
    a["json"] = False
    i, rest = 0, []
    while i < len(argv):
        x = argv[i]
        if x == "--json":
            a["json"] = True
        elif x in flags:
            if i + 1 >= len(argv) or argv[i + 1].startswith("--"):
                raise ValueError(f"{x} needs a value")
            key = flags[x]
            if key in multi:
                a[key].append(argv[i + 1])
            else:
                a[key] = argv[i + 1]
            i += 1
        elif x in ("-h", "--help"):
            raise SystemExit(print(__doc__) or 0)
        else:
            rest.append(x)
        i += 1
    return a, rest


def main(argv):
    try:
        a, rest = parse(argv)
        if rest:
            raise ValueError(f"unexpected argument '{rest[0]}'")
    except ValueError as e:
        print(f"ui_catalog: {e}\n{__doc__}", file=sys.stderr)
        return 2
    cat = build(a["uitoolkit"], a["ref"], a["project"])
    if a["kind"]:
        cat["entries"] = [e for e in cat["entries"] if e["kind"] in a["kind"]]
    print(json.dumps(cat, indent=1) if a["json"] else markdown(cat))
    return 0 if cat["status"] == "PASS" else 1


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):  # Windows pipes default to cp1252: output is UTF-8 everywhere
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
