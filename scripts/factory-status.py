#!/usr/bin/env python3
"""factory-status - pending cross-repo work, derived from the repositories themselves.

No workflow database: every line is recomputed from git refs, tags, manifests, lock files and
contract copies, so it survives crashes, restarts and partial completion. Read-only.

Sections
  Contracts   consistency on the integration branches (origin/<default> when present, else the
              local default branch) - the view the product CIs compare:
                wire-generated    server C# binding == Netcode Wire.cs; wire.proto not newer than its bindings
                protocol-version  C# / Go / Netcode constants equal
                gamestate-migrations  embedded migrations == deploy copies (normalised like Migrator.cs)
  Wire rollout  server wire change -> Netcode copy -> Netcode release -> client pin
  Packages    per package: latest tag, commits since it (unreleased), package.json vs tag,
              CHANGELOG section (READY_TO_TAG when bumped + dated + clean)
  Pins        client pin vs latest upstream tag (released, not propagated); SGL watchers (package CIs)
  CI pins     package CIs that install another package / SGL at a fixed ref (contract watchers)
              compared with the client pin and the latest tag
  In flight   local <type>/<area>/<topic> branches ahead of the default branch, grouped by topic
              across repos (one cross-repo task = one topic name)
  Worktrees   uncommitted work per repo (where an interrupted implementation lives)
  Clones      embedded package clones inside the client (user state, not the canonical checkout)
  Evidence    stored check results per repo, graded against the current tree (STALE = outdated)
  Freshness   age of each repo's last fetch: origin/* conclusions are only as new as that fetch.
              Nothing is fetched here; run the printed `git fetch` yourself when it matters.
  Pending     ordered follow-ups with the owning skill

Usage: factory-status.py [--json] [--strict] [--remote]
  --strict  exit 1 when anything is pending   --remote  also check unity-build-workflows via ls-remote
  RPG_FACTORY_FETCH_MAX_AGE_H (default 24): older fetches are reported as stale remote knowledge
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_ROOT = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.path.dirname(HERE)
REG = json.load(open(os.path.join(PLUGIN_ROOT, "registry.json"), encoding="utf-8"))
WS = os.environ.get(REG["workspace"]["root_env"]) or REG["workspace"]["root_default"]
sys.path.insert(0, os.path.join(HERE, "lib"))
import evidence  # noqa: E402
REPO_BY_NAME = {}
for _k, _r in REG["repos"].items():
    _m = re.search(r"github\.com[:/][^/]+/([^/.]+)", _r.get("remote", ""))
    if _m:
        REPO_BY_NAME[_m.group(1).lower()] = _k

SERVER_CS = "backend/gameserver-dotnet/GameServer/Net/Generated/RpgMmo/Wire/V1/Wire.cs"
NETCODE_CS = "Runtime/Protocol/Generated/Wire.cs"
PROTO = "backend/shared/proto/wire.proto"
PROTO_GEN = ["backend/shared/proto/gen/", "backend/gameserver-dotnet/GameServer/Net/Generated/"]
VERSION_FILES = {"server-cs": ("server", "backend/gameserver-dotnet/GameServer/Net/WireProtocol.cs", r"const uint ProtocolVersion\s*=\s*(\d+)"),
                 "server-go": ("server", "backend/shared/messages/messages.go", r"const WireProtocolVersion uint32\s*=\s*(\d+)"),
                 "netcode": ("netcode", "Runtime/Protocol/WireProtocolVersion.cs", r"const uint Current\s*=\s*(\d+)")}
MIG = ("backend/gameserver-dotnet/GameServer/Persistence/Migrations", "backend/deploy/db/migrations/gamestate", "backend/deploy/db/init-gamestate.sql")
PACKAGES = {"netcode": "com.cuvara.netcode", "unitydots": "com.cuvara.dots", "uitoolkit": "com.cuvara.uitoolkit"}


def rdir(key):
    return os.path.join(WS, REG["repos"][key]["path"])


def git(key_or_dir, *args):
    d = rdir(key_or_dir) if key_or_dir in REG["repos"] else key_or_dir
    try:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def present(key):
    return os.path.isdir(os.path.join(rdir(key), ".git"))


@lru_cache(maxsize=None)
def integ(key):
    """Integration ref: origin/<default> if it exists, else the local default branch."""
    d = REG["repos"][key]["default_branch"]
    return f"origin/{d}" if git(key, "rev-parse", "--verify", "-q", f"origin/{d}") else d


def show(key, ref, path):
    return git(key, "show", f"{ref}:{path}")


@lru_cache(maxsize=None)
def tags(key, prefix):
    out = git(key, "tag", "-l", f"{prefix}*", "--sort=-v:refname") or ""
    return [t for t in out.split() if re.match(re.escape(prefix) + r"\d", t)]


def normalise_sql(text):
    lines = [l for l in text.splitlines() if not l.strip().startswith("--")]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def main():
    as_json, strict, remote = "--json" in sys.argv, "--strict" in sys.argv, "--remote" in sys.argv
    keys = [k for k in REG["repos"] if present(k)]
    pool = ThreadPoolExecutor(max_workers=len(keys) or 1)  # working-tree scans overlap with the ref work below
    status_futures = {k: pool.submit(lambda k=k: git(k, "status", "--porcelain=v1", "--ignore-submodules=dirty") or "") for k in keys}
    st = {"workspace": WS, "contracts": [], "wire_rollout": [], "packages": [], "pins": [], "in_flight": [], "pending": []}
    pend = st["pending"]

    # ---- contracts on integration branches
    if present("server") and present("netcode"):
        sref, nref = integ("server"), integ("netcode")
        a, b = show("server", sref, SERVER_CS), show("netcode", nref, NETCODE_CS)
        same = a is not None and a == b
        st["contracts"].append({"id": "wire-generated", "ok": same,
                                "detail": f"server {sref}:{SERVER_CS} {'==' if same else '!='} netcode {nref}:{NETCODE_CS}"})
        pt = (git("server", "log", "-1", "--format=%ct", sref, "--", PROTO) or "0").strip() or "0"
        gt = (git("server", "log", "-1", "--format=%ct", sref, "--", *PROTO_GEN) or "0").strip() or "0"
        gen_ok = int(pt) <= int(gt)
        st["contracts"].append({"id": "wire-generated/bindings", "ok": gen_ok,
                                "detail": "wire.proto last change is not newer than its generated bindings" if gen_ok
                                else "wire.proto changed after the last commit to its generated bindings - regenerate (generate.sh)"})
        if not gen_ok:
            pend.append({"skill": "wire-contract", "repo": "server", "what": "regenerate Go/C# bindings from wire.proto (generate.sh, protoc 29.3)"})
        vals = {}
        for k, (repo, path, rx) in VERSION_FILES.items():
            txt = show(repo, integ(repo), path) or ""
            m = re.search(rx, txt)
            vals[k] = int(m.group(1)) if m else None
        vok = len(set(vals.values())) == 1 and None not in vals.values()
        st["contracts"].append({"id": "protocol-version", "ok": vok, "detail": ", ".join(f"{k}={v}" for k, v in vals.items())})
        if not vok:
            pend.append({"skill": "wire-contract", "repo": "server+netcode", "what": f"protocol version constants disagree ({vals})"})
    if present("server"):
        sref = integ("server")
        emb = (git("server", "ls-tree", "--name-only", f"{sref}:{MIG[0]}") or "").split()
        dep = (git("server", "ls-tree", "--name-only", f"{sref}:{MIG[1]}") or "").split()
        emb_sql = sorted(x for x in emb if x.endswith(".sql"))
        dep_sql = sorted(x for x in dep if x.endswith(".sql"))
        diff = [f for f in sorted(set(emb_sql) | set(dep_sql))
                if f not in emb_sql or f not in dep_sql
                or normalise_sql(show("server", sref, f"{MIG[0]}/{f}") or "") != normalise_sql(show("server", sref, f"{MIG[1]}/{f}") or "")]
        mok = not diff and bool(emb_sql)
        st["contracts"].append({"id": "gamestate-migrations", "ok": mok,
                                "detail": f"{len(emb_sql)} embedded / {len(dep_sql)} deploy copies" + (f"; differ: {', '.join(diff)}" if diff else "")})
        if not mok:
            pend.append({"skill": "server-services", "repo": "server", "what": f"migration copies out of sync: {', '.join(diff) or 'none found'}"})
    for c in st["contracts"]:
        if not c["ok"] and c["id"] == "wire-generated":
            pass  # expanded by the rollout chain below

    # ---- wire rollout chain
    if present("server") and present("netcode") and present("client"):
        sref, nref = integ("server"), integ("netcode")
        s_cs = show("server", sref, SERVER_CS)
        n_dev = show("netcode", nref, NETCODE_CS)
        ntags = tags("netcode", "v")
        n_rel = show("netcode", ntags[0], NETCODE_CS) if ntags else None
        pin = (json.loads(show("client", integ("client"), "Packages/packages-lock.json") or "{}").get("dependencies", {})
               .get("com.cuvara.netcode", {}).get("version", ""))
        pin_tag = pin.rsplit("#", 1)[-1] if "#" in pin else None
        pinned = show("netcode", pin_tag, NETCODE_CS) if pin_tag else None
        h = lambda x: hashlib.sha256(x.encode()).hexdigest()[:10] if x else "-"
        stages = [
            {"stage": "server bindings", "ok": s_cs is not None, "detail": f"server {sref} Wire.cs {h(s_cs)}", "skill": "wire-contract"},
            {"stage": "Netcode copy (develop)", "ok": s_cs == n_dev, "detail": f"netcode {nref} Wire.cs {h(n_dev)}", "skill": "unity-package"},
            {"stage": "Netcode release (tag)", "ok": s_cs == n_rel, "detail": f"latest tag {ntags[0] if ntags else '-'} Wire.cs {h(n_rel)}", "skill": "unity-package"},
            {"stage": "client pin", "ok": s_cs == pinned, "detail": f"client pins netcode {pin_tag or '-'} Wire.cs {h(pinned)}", "skill": "pin-bump"},
        ]
        st["wire_rollout"] = stages
        first_bad = next((s for s in stages if not s["ok"]), None)
        if first_bad:
            i = stages.index(first_bad)
            what = {1: "copy the server's generated Wire.cs into Netcode (byte-identical) and validate",
                    2: "Netcode develop carries the new wire but no tag does: READY_TO_TAG Netcode (the lead tags)",
                    3: "a Netcode release carries the new wire but the client still pins an older one: pin-bump"}.get(i, "server bindings missing")
            pend.append({"skill": first_bad["skill"], "repo": ["server", "netcode", "netcode", "client"][i],
                         "what": f"wire rollout incomplete at '{first_bad['stage']}': {what}"})
            for later in stages[i + 1:]:
                later["ok"] = False if later["ok"] is False else later["ok"]

    # ---- packages
    client_lock = {}
    if present("client"):
        client_lock = json.loads(show("client", integ("client"), "Packages/packages-lock.json") or "{}").get("dependencies", {})
    for key, pkg in PACKAGES.items():
        if not present(key):
            continue
        ref = integ(key)
        t = tags(key, "v")
        latest = t[0] if t else None
        ahead = int((git(key, "rev-list", "--count", f"{latest}..{ref}") or "0").strip() or 0) if latest else None
        pj = json.loads(show(key, ref, "package.json") or "{}")
        ver = pj.get("version")
        cl = (show(key, ref, "CHANGELOG.md") or "")
        dated = bool(re.search(r"^## \[" + re.escape(ver or "x") + r"\]\s*-\s*\d{4}-\d{2}-\d{2}", cl, re.M))
        tagged = bool(ver) and f"v{ver}" in t
        state = ("released" if ahead == 0 else
                 "READY_TO_TAG" if (not tagged and dated and ahead) else
                 "unreleased changes" if ahead else "unknown")
        pin = client_lock.get(pkg, {}).get("version", "")
        pin_tag = pin.rsplit("#", 1)[-1] if "#" in pin else None
        st["packages"].append({"repo": key, "package": pkg, "integration_ref": ref, "latest_tag": latest, "commits_since_tag": ahead,
                               "package_json": ver, "changelog_dated": dated, "state": state, "client_pin": pin_tag})
        if state == "READY_TO_TAG":
            pend.append({"skill": "unity-package", "repo": key, "what": f"READY_TO_TAG {key} v{ver} ({ahead} commit(s) since {latest}) - the lead tags, then pin-bump"})
        elif state == "unreleased changes":
            pend.append({"skill": "unity-package", "repo": key, "what": f"{ahead} commit(s) on {ref} since {latest}; package.json {ver} "
                         + ("already tagged - bump version + dated CHANGELOG section to release" if tagged else "not yet dated/released")})
        if latest and pin_tag and pin_tag != latest:
            st["pins"].append({"package": pkg, "pinned": pin_tag, "latest": latest})
            pend.append({"skill": "pin-bump", "repo": "client", "what": f"{pkg}: released {latest} not propagated (client pins {pin_tag})"})

    # ---- SGL
    if present("server") and present("client"):
        sref = integ("server")
        sgl = tags("server", "sgl-v")
        latest = sgl[0] if sgl else None
        sgl_path = "backend/gameserver-dotnet/Shared.GameLogic"
        ahead = int((git("server", "rev-list", "--count", f"{latest}..{sref}", "--", sgl_path) or "0").strip() or 0) if latest else None
        pin = client_lock.get("com.rpgmmo.shared-gamelogic", {}).get("version", "")
        pin_tag = pin.rsplit("#", 1)[-1] if "#" in pin else None
        watchers = {}
        for c in REG["contracts"]:
            if c["id"] == "sgl-pin":
                for w in c.get("watchers", []):
                    if present(w["repo"]):
                        m = re.findall(r"#(sgl-v[\d.]+)", show(w["repo"], integ(w["repo"]), w["path"]) or "")
                        watchers[w["repo"]] = sorted(set(m))
        st["pins"].append({"package": "com.rpgmmo.shared-gamelogic", "pinned": pin_tag, "latest": latest,
                           "sgl_commits_since_tag": ahead, "ci_watchers": watchers})
        if ahead:
            pend.append({"skill": "server-realtime", "repo": "server", "what": f"Shared.GameLogic: {ahead} commit(s) since {latest} - release = package.json bump, the lead tags sgl-v*"})
        if latest and pin_tag and pin_tag != latest:
            pend.append({"skill": "pin-bump", "repo": "client", "what": f"SGL {latest} released, client pins {pin_tag}"})
        lag = {r: v for r, v in watchers.items() if pin_tag and any(x != pin_tag for x in v)}
        if lag:
            pend.append({"skill": "unity-package", "repo": ",".join(lag), "what": f"package CI bootstraps SGL {lag} while the client pins {pin_tag}"})

    # ---- submodule pointer (unity-build-workflows) - needs the network
    if remote and present("client"):
        line = [l for l in (git("client", "ls-tree", integ("client"), "unity-build-workflows") or "").splitlines()]
        sha = line[0].split()[2] if line else None
        out = subprocess.run(["git", "ls-remote", "--tags", "https://github.com/Cuvara/unity-build-workflows"],
                             capture_output=True, text=True, timeout=60).stdout if sha else ""
        tagmap = {l.split()[1].replace("refs/tags/", "").replace("^{}", ""): l.split()[0] for l in out.splitlines() if l.strip()}
        at = [t for t, s in tagmap.items() if s == sha]
        st["pins"].append({"package": "unity-build-workflows (submodule)", "pinned": sha[:10] if sha else None,
                           "tags_at_pin": at, "latest": sorted(tagmap, key=lambda x: [int(n) for n in re.findall(r"\d+", x)] or [0])[-1] if tagmap else None})

    # ---- reusable-workflow refs (what client CI actually runs) - local, no network
    if present("client"):
        refs = {}
        ref = integ("client")
        hits = git("client", "grep", "-E", r"uses:\s*Cuvara/unity-build-workflows/", ref, "--", ".github/workflows/") or ""
        for line in hits.splitlines():  # <ref>:<path>:<line>
            parts = line.split(":", 2)
            m = re.search(r"uses:\s*Cuvara/unity-build-workflows/\S+@(\S+)", parts[2] if len(parts) > 2 else "")
            if m:
                refs.setdefault(m.group(1), []).append(parts[1].rsplit("/", 1)[-1])
        if refs:
            st["pins"].append({"package": "unity-build-workflows (workflow refs)", "refs": {k: sorted(set(v)) for k, v in refs.items()}})
            majors = sorted({r for r in refs if re.match(r"^v\d+$", r)})
            if len(majors) > 1:
                pend.append({"skill": "pin-bump", "repo": "client", "what": f"client workflows call unity-build-workflows at mixed majors {majors}"})
            if remote and majors:
                out = subprocess.run(["git", "ls-remote", "--tags", "https://github.com/Cuvara/unity-build-workflows"],
                                     capture_output=True, text=True, timeout=60).stdout
                newest = max([int(t) for t in re.findall(r"refs/tags/v(\d+)$", out, re.M)] or [0])
                used = max(int(m[1:]) for m in majors)
                if newest > used:
                    pend.append({"skill": "pin-bump", "repo": "client", "what": f"unity-build-workflows v{newest} released, client workflows use v{used}"})

    # ---- package CIs pinning other packages / SGL (contract watchers): drift vs the client pin
    lock_pins = {}
    for pkg, v in client_lock.items():
        if isinstance(v, dict) and "#" in str(v.get("version", "")):
            lock_pins[pkg] = v["version"].rsplit("#", 1)[-1]
    pkg_of = {k: v for k, v in PACKAGES.items()}
    st["ci_pins"] = []
    seen_w = set()
    for c in REG["contracts"]:
        for w in c.get("watchers") or []:
            if (w["repo"], w["path"]) in seen_w or not present(w["repo"]):
                continue
            seen_w.add((w["repo"], w["path"]))
            text = show(w["repo"], integ(w["repo"]), w["path"]) or ""
            for m in re.finditer(r"github\.com/Cuvara/([A-Za-z0-9_-]+)\.git(\?path=[^#\"'\s]*)?#([\w.-]+)", text):
                target = REPO_BY_NAME.get(m.group(1).lower())
                if not target or target == w["repo"]:
                    continue
                pkg = "com.rpgmmo.shared-gamelogic" if m.group(2) else pkg_of.get(target)
                ref = m.group(3)
                client_pin = lock_pins.get(pkg)
                latest = (tags(target, "sgl-v") if m.group(2) else tags(target, "v"))
                entry = {"watcher": f"{w['repo']}:{w['path']}", "package": pkg, "ref": ref, "client_pin": client_pin,
                         "latest": latest[0] if latest else None}
                if entry not in st["ci_pins"]:
                    st["ci_pins"].append(entry)
    for e in st["ci_pins"]:
        if e["client_pin"] and e["ref"] != e["client_pin"] and not e["package"].endswith("shared-gamelogic"):
            pend.append({"skill": "unity-package", "repo": e["watcher"].split(":")[0],
                         "what": f"package CI ({e['watcher']}) tests against {e['package']}#{e['ref']} while the client pins {e['client_pin']}"})

    # ---- freshness of remote knowledge (no fetch here)
    max_age = float(os.environ.get("RPG_FACTORY_FETCH_MAX_AGE_H", "24"))
    st["freshness"] = {}
    for key in REG["repos"]:
        if not present(key):
            continue
        gd = (git(key, "rev-parse", "--path-format=absolute", "--git-dir") or "").strip()
        fh = os.path.join(gd, "FETCH_HEAD") if gd else ""
        age = round((time.time() - os.path.getmtime(fh)) / 3600, 1) if fh and os.path.exists(fh) else None
        uses_origin = integ(key).startswith("origin/")
        stale = uses_origin and (age is None or age > max_age)
        st["freshness"][key] = {"integration_ref": integ(key), "last_fetch_h": age, "stale": stale}
    stale_repos = [k for k, f in st["freshness"].items() if f["stale"]]
    if stale_repos:
        pend.append({"skill": "factory-core", "repo": ",".join(stale_repos),
                     "what": "remote knowledge older than %sh (or never fetched): contract/rollout/package results use those origin/* refs. "
                             "Refresh (read-only for working trees): %s" % (int(max_age), "; ".join(
                                 f"git -C {rdir(k)} fetch origin" for k in stale_repos))})

    # ---- uncommitted work per repo, embedded clones, stored evidence
    st["worktrees"], st["clones"], st["evidence"] = {}, [], {}
    statuses = {k: f.result() for k, f in status_futures.items()}
    pool.shutdown()
    for key in keys:
        rep = REG["repos"][key]
        porcelain = statuses[key].splitlines()
        st["worktrees"][key] = {"branch": (git(key, "branch", "--show-current") or "").strip() or "(detached)",
                                "tracked_changes": sum(1 for l in porcelain if not l.startswith("??")),
                                "untracked": sum(1 for l in porcelain if l.startswith("??"))}
        for cl in rep.get("embedded_clones", []):
            cd = os.path.join(rdir(key), cl["path"])
            if os.path.exists(os.path.join(cd, ".git")):
                st["clones"].append({"in": key, "path": cl["path"], "of": cl["of"],
                                     "head": (git(cd, "rev-parse", "--short", "HEAD") or "").strip(),
                                     "branch": (git(cd, "branch", "--show-current") or "").strip(),
                                     "canonical_head": (git(cl["of"], "rev-parse", "--short", "HEAD") or "").strip() if present(cl["of"]) else None})
        recs = evidence.all_latest(WS, key)
        if recs:
            rows = []
            defs = {(m["id"], c["id"]): c for m in REG["modules"] for t in ("fast", "extended") for c in m["checks"][t]}
            for rec in recs:
                chk = rec.get("definition") or {**defs.get((rec.get("module"), rec.get("check")), {}), "run": rec.get("command"), "cwd": rec.get("cwd")}
                state, detail = evidence.assess(rec, rdir(key), chk)
                rows.append({"check": f"{rec.get('module')}/{rec.get('check')}", "state": state, "detail": detail})
            st["evidence"][key] = rows

    # ---- in-flight topic branches
    topics = {}
    for key, rep in REG["repos"].items():
        if not present(key):
            continue
        base = integ(key)
        for br in (git(key, "for-each-ref", "--format=%(refname:short)", "refs/heads") or "").split():
            if br in rep["protected_branches"] or not re.match(r"^[a-z]+/[^/]+/.+", br):
                continue
            ahead = int((git(key, "rev-list", "--count", f"{base}..{br}") or "0").strip() or 0)
            if ahead == 0:
                continue
            files = [f for f in (git(key, "diff", "--name-only", f"{base}...{br}") or "").splitlines() if f]
            topic = br.split("/", 2)[2]
            topics.setdefault(topic, []).append({"repo": key, "branch": br, "ahead": ahead, "files": len(files),
                                                 "touches_wire": any(f.startswith("backend/shared/proto/") or f.endswith("Generated/Wire.cs") for f in files)})
    for topic, items in sorted(topics.items()):
        st["in_flight"].append({"topic": topic, "branches": items})
        if len(items) > 1 or any(i["touches_wire"] for i in items):
            repos = {i["repo"] for i in items}
            if any(i["touches_wire"] for i in items):
                missing = [r for r in ("server", "netcode", "client") if r not in repos]
                if missing:
                    pend.append({"skill": "wire-contract", "repo": ",".join(missing),
                                 "what": f"topic '{topic}' changes the wire in {', '.join(sorted(repos))} but has no branch in {', '.join(missing)} yet"})

    # ---- render
    if as_json:
        print(json.dumps(st, indent=2))
    else:
        mark = lambda ok: "OK " if ok else "!! "
        print(f"# Factory status (derived from git; workspace {WS})\n")
        print("## Contracts (integration branches)")
        for c in st["contracts"]:
            print(f"- {mark(c['ok'])}{c['id']}: {c['detail']}")
        if st["wire_rollout"]:
            print("\n## Wire rollout")
            print(" -> ".join(f"{s['stage']} {'OK' if s['ok'] else 'PENDING'}" for s in st["wire_rollout"]))
        print("\n## Packages")
        for p in st["packages"]:
            print(f"- {p['repo']}: {p['state']} (latest {p['latest_tag']}, +{p['commits_since_tag']} on {p['integration_ref']}, "
                  f"package.json {p['package_json']}, client pins {p['client_pin']})")
        print("\n## Pins")
        for p in st["pins"]:
            if "refs" in p:
                print(f"- {p['package']}: " + ", ".join(f"@{r} in {len(fs)} workflow(s)" for r, fs in p["refs"].items()))
                continue
            print(f"- {p['package']}: client {p.get('pinned')} / latest {p.get('latest')}"
                  + (f" / SGL commits since tag {p['sgl_commits_since_tag']}" if "sgl_commits_since_tag" in p else "")
                  + (f" / CI watchers {p['ci_watchers']}" if p.get("ci_watchers") else ""))
        if st["ci_pins"]:
            print("\n## Package CI pins (watchers)")
            for e in st["ci_pins"]:
                print(f"- {e['watcher']}: {e['package']}#{e['ref']} (client {e['client_pin']}, latest {e['latest']})")
        print("\n## Working trees (uncommitted work - where an interrupted task resumes)")
        for k, w in st["worktrees"].items():
            print(f"- {k}: {w['branch']}, {w['tracked_changes']} tracked change(s), {w['untracked']} untracked")
        for c in st["clones"]:
            print(f"- embedded clone {c['in']}/{c['path']} (of {c['of']}): {c['branch'] or 'detached'} @{c['head']} - user state, "
                  f"not the canonical {c['of']} checkout (@{c['canonical_head']}); never edit or reset it")
        if st["evidence"]:
            print("\n## Validation evidence (graded against the current tree)")
            for k, rows in st["evidence"].items():
                for r in rows:
                    print(f"- {k} {r['check']}: {r['state']} - {r['detail'].split('; log ')[0]}")
        print("\n## Freshness (remote knowledge = last fetch; nothing fetched here)")
        print("- " + "; ".join(f"{k} {f['integration_ref']} " + (f"fetched {f['last_fetch_h']}h ago" if f["last_fetch_h"] is not None else "never fetched")
                               + (" STALE" if f["stale"] else "") for k, f in st["freshness"].items()))
        print("\n## In flight (local <type>/<area>/<topic> branches ahead of the default branch)")
        for t in st["in_flight"]:
            print(f"- {t['topic']}: " + "; ".join(f"{b['repo']} {b['branch']} +{b['ahead']}" + (" (wire)" if b["touches_wire"] else "") for b in t["branches"]))
        if not st["in_flight"]:
            print("- none")
        print("\n## Pending (resume here; owning skill in brackets)")
        for p in pend:
            print(f"- [{p['skill']}] {p['repo']}: {p['what']}")
        if not pend:
            print("- nothing pending")
    return 1 if (strict and pend) else 0


if __name__ == "__main__":
    sys.exit(main())
