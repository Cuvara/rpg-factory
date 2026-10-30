#!/usr/bin/env python3
"""Plan, inspect, dispatch and report registry-routed artifact workflows."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "lib"))
from context import handoff_graph


def die(message, code=2):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def read_spec(path):
    raw = Path(path).read_text(encoding="utf-8")
    if path.endswith((".yaml", ".yml")):
        die("YAML workflow specs are unsupported; use JSON front matter or a JSON file")
    if path.endswith(".md"):
        match = re.match(r"\A---json\s*\n(.*?)\n---", raw, re.S)
        if not match:
            die("Markdown workflow spec needs strict JSON front matter (---json ... ---)")
        raw = match.group(1)
    try:
        spec = json.loads(raw)
    except ValueError as exc:
        die(f"invalid workflow JSON: {exc}")
    for key in ("id", "title", "goal", "targets", "existing"):
        if key not in spec:
            die(f"workflow spec missing {key}")
    return spec


def load_registry(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def kind_domains(reg):
    found = {}
    for domain, data in reg.get("domains", {}).items():
        for kind in data.get("artifact_kinds", []):
            found.setdefault(kind, []).append(domain)
    return found


def path_module(reg, repo, path):
    path = path.replace("\\", "/").strip("/")
    choices = []
    for module in reg.get("modules", []):
        if module.get("repo") != repo:
            continue
        for prefix in module.get("paths", []):
            prefix = prefix.strip("/")
            if not prefix or path == prefix or path.startswith(prefix + "/"):
                choices.append((len(prefix), module))
    return max(choices, key=lambda x: x[0])[1] if choices else None


def artifacts(authoring):
    found = {}
    if not authoring or not Path(authoring).is_dir():
        return found
    for path in Path(authoring).rglob("*"):
        if not path.is_file() or ".git" in path.parts or "approvals" in path.parts:
            continue
        try:
            raw = path.read_text(encoding="utf-8")
            if path.suffix == ".json":
                obj = json.loads(raw)
            elif raw.startswith("---json"):
                m = re.match(r"\A---json\s*\n(.*?)\n---", raw, re.S)
                obj = json.loads(m.group(1)) if m else None
            else:
                continue
            if isinstance(obj, dict) and obj.get("id"):
                rev = subprocess.run(["git", "-C", str(authoring), "rev-parse", f"HEAD:{path.relative_to(authoring).as_posix()}"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
                if not re.fullmatch(r"[0-9a-f]{40,64}", rev):
                    rev = hashlib.sha1(path.read_bytes()).hexdigest()
                found[obj["id"]] = {"id": obj["id"], "rev": rev, "status": obj.get("status", "draft"), "domain": obj.get("domain"), "kind": obj.get("kind"), "path": path.relative_to(authoring).as_posix(), "sources": obj.get("sources", []), "upstream": obj.get("upstream", [])}
        except (OSError, ValueError):
            continue
    return found


def build(spec, reg, authoring):
    kd = kind_domains(reg)
    existing = artifacts(authoring)
    ids = set(spec.get("existing", []))
    nodes = {}
    edges = set()
    handoffs = [c for c in reg.get("contracts", []) if c.get("kind") == "handoff"]
    def make_node(node_id, kind, domain, title, acceptance, repo="authoring", paths=None, target=False):
        if node_id not in nodes:
            module = path_module(reg, repo, (paths or [""])[0])
            skill = reg.get("domains", {}).get(domain, {}).get("lead") or (module.get("skills", [None])[0] if module else None)
            output = list(paths or [])
            if repo == "authoring" and output:
                output = [output[0].rstrip("/") + "/" + node_id + ".artifact.json"]
            nodes[node_id] = {"id": node_id, "domain": domain, "lead_skill": skill, "kind": kind, "title": title or node_id, "repo": repo, "paths": output, "acceptance": acceptance or [], "inputs": [], "target": target, "checks": sorted(set(x.get("id") for x in ((module or {}).get("checks", {}).get("fast", []) + (module or {}).get("checks", {}).get("extended", [])))), "artifact_id": node_id if repo == "authoring" else None, "rev": existing.get(node_id, {}).get("rev")}
        return nodes[node_id]
    for index, target in enumerate(spec["targets"]):
        kind = target["kind"]
        if kind == "implementation":
            repo = target.get("repo")
            paths = target.get("paths", [])
            if not repo or repo not in reg.get("repos", {}) or not paths:
                die(f"implementation target {target.get('id', index)} needs a registered repo and paths")
            if any(not path_module(reg, repo, p) for p in paths):
                die(f"implementation target path is not registered for {repo}: {paths}")
            domain = "engineering"
        else:
            candidates = kd.get(kind, [])
            if target.get("domain"):
                candidates = [d for d in candidates if d == target["domain"]]
            if len(candidates) != 1:
                die(f"artifact kind '{kind}' is {'unknown' if not candidates else 'ambiguous'}; candidates: {', '.join(candidates) or 'none'}", 3)
            domain = candidates[0]
            target = dict(target, repo="authoring")
            slug = {"feature-spec": "features"}.get(kind, kind.replace("-", ""))
            module = next((m for m in reg.get("modules", []) if m.get("repo") == "authoring" and m.get("domain") == domain and slug in m.get("id", "").replace("-", "")), None)
            paths = list((module or {}).get("paths", []))[:1]
        node_id = target.get("id") or f"{kind}-{index + 1}"
        make_node(node_id, kind, domain, target.get("title"), target.get("acceptance"), target.get("repo", "authoring"), paths, True)
        nodes[node_id]["sources"] = target.get("sources", [])
    # If a requested domain is downstream of a registered artifact handoff, add its
    # source artifact unless a usable approved artifact is already present.
    while True:
      prior_nodes = len(nodes)
      for target_node in list(nodes.values()):
        for contract in handoffs:
            if contract.get("domain") == target_node["domain"]:
                continue
            source = contract.get("source", {})
            source_domain = contract.get("domain") or (path_module(reg, source.get("repo"), source.get("path", "")) or {}).get("domain")
            if not source_domain or any(n["domain"] == source_domain for n in nodes.values()):
                continue
            reaches_target = any((path_module(reg, end.get("repo"), end.get("path", "")) or {}).get("domain") == target_node["domain"] for end in contract.get("copies", []))
            if not reaches_target:
                continue
            source_module = path_module(reg, source.get("repo"), source.get("path", ""))
            module_id = (source_module or {}).get("id", "").replace("-", "")
            source_kind = next((k for k in reg.get("domains", {}).get(source_domain, {}).get("artifact_kinds", []) if {"feature-spec": "features"}.get(k, k.replace("-", "")) in module_id), None)
            if not source_kind:
                continue
            usable = next((x for x in existing.values() if x.get("kind") == source_kind and x.get("domain") == source_domain and x.get("status") in ("approved", "in-implementation", "verified", "released")), None)
            if usable:
                if not any(x.get("id") == usable["id"] for x in target_node["inputs"]):
                    target_node["inputs"].append({"id": usable["id"], "rev": usable["rev"]})
                continue
            upstream_id = "upstream-" + contract["id"]
            upstream = make_node(upstream_id, source_kind, source_domain, source_kind, ["Satisfy handoff " + contract["id"]], "authoring", [source.get("path", "")], False)
            if not any(x.get("id") == upstream_id for x in target_node["inputs"]):
                target_node["inputs"].append({"id": upstream_id, "rev": upstream.get("rev")})
            edges.add((upstream_id, target_node["id"]))
      if len(nodes) == prior_nodes:
          break
    # Resolve explicit sources as ids. Existing ids are carried by reference, never copied.
    for node in list(nodes.values()):
        for source in node.get("sources", []):
            if source in nodes:
                edges.add((source, node["id"]))
            elif source not in ids and source not in existing:
                die(f"missing dependency artifact {source} required by {node['id']}", 3)
            else:
                node["inputs"].append({"id": source, "rev": existing.get(source, {}).get("rev")})
    # Handoff edges relate source and destination domains using registered module paths.
    for source in list(nodes.values()):
        for contract in handoffs:
            if contract.get("domain") != source["domain"]:
                continue
            for end in contract.get("copies", []):
                dest = path_module(reg, end.get("repo"), end.get("path", ""))
                domain = (dest or {}).get("domain", "engineering")
                candidates = [n for n in nodes.values() if n["domain"] == domain and n["id"] != source["id"]]
                if not candidates:
                    continue
                for dst in candidates:
                    edges.add((source["id"], dst["id"]))
                    if source["artifact_id"]:
                        dst["inputs"].append({"id": source["artifact_id"], "rev": source.get("rev")})
    # Engineering handoff target is required when a contract ends in Engineering.
    for source in list(nodes.values()):
        for contract in handoffs:
            if contract.get("domain") != source["domain"]:
                continue
            for end in contract.get("copies", []):
                dest = path_module(reg, end.get("repo"), end.get("path", ""))
                if (dest or {}).get("domain", "engineering") == "engineering":
                    impl = next((n for n in nodes.values() if n["kind"] == "implementation" and n["repo"] == end.get("repo")), None)
                    if impl:
                        edges.add((source["id"], impl["id"])); impl["inputs"].append({"id": source["artifact_id"], "rev": source.get("rev")})
    # include only input artifacts already declared on the spec or observed in authoring
    for node in nodes.values():
        for item in node["inputs"]:
            if item["id"] in existing:
                item["rev"] = existing[item["id"]]["rev"]
    # Shared output paths are exclusive resources, so order their writers even when
    # their artifact dependencies would otherwise place them in the same wave.
    writers = sorted(nodes.values(), key=lambda n: n["id"])
    for i, left in enumerate(writers):
        for right in writers[i + 1:]:
            if left["repo"] != right["repo"]:
                continue
            overlap = any(a == b or a.startswith(b.rstrip("/") + "/") or b.startswith(a.rstrip("/") + "/") for a in left["paths"] for b in right["paths"])
            if overlap:
                edges.add((left["id"], right["id"]))
    indegree = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for a,b in edges:
        indegree[b] += 1; adj[a].append(b)
    waves=[]; ready=sorted(n for n,d in indegree.items() if d==0); done=[]
    while ready:
        wave=ready; waves.append(wave); done.extend(wave); next_ready=[]
        for n in wave:
            for b in adj[n]:
                indegree[b]-=1
                if indegree[b]==0: next_ready.append(b)
        ready=sorted(next_ready)
    if len(done)!=len(nodes):
        cycle=next((a for a,d in indegree.items() if d), "unknown")
        die("CYCLE: " + " -> ".join([cycle] + [b for b in adj[cycle] if indegree[b]]), 3)
    for wave in waves:
        # serialize overlapping output paths within a wave
        serialized=[]; seen=set()
        for nid in wave:
            key=(nodes[nid]["repo"], tuple(nodes[nid]["paths"]))
            if key in seen: serialized.append([nid])
            else: seen.add(key); serialized.append([nid])
        wave[:] = [n for group in serialized for n in group]
    return {"schema":"rpg-factory.workflow-plan/1","workflow":spec,"nodes":nodes,"edges":[{"from":a,"to":b} for a,b in sorted(edges)],"waves":waves,"existing":existing}


def quality(authoring, reg_path, repos, involved):
    if not authoring or not Path(authoring).is_dir(): return {}
    cmd=[sys.executable,"-B",str(ROOT/"scripts/checks/artifact-quality.py"),authoring,"--registry",reg_path,"--json"]
    for item in repos: cmd += ["--repos",item]
    p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8")
    try: data=json.loads(p.stdout)
    except ValueError: return {}
    grouped = {}
    for result in data.get("results", []):
        if result.get("artifact") in involved:
            grouped.setdefault(result["artifact"], {"results": []})["results"].append(result)
    return grouped


def state_for(node, plan, quality_map):
    artifact=plan["existing"].get(node.get("artifact_id") or node["id"])
    if not artifact:
        return "missing"
    if artifact["status"] == "rejected": return "draft" # recoverable only by explicit authoring edit
    if artifact["status"] == "blocked": return "blocked"
    upstream=[e["from"] for e in plan["edges"] if e["to"]==node["id"]]
    stale=[u for u in upstream if plan["nodes"][u].get("rev") and any(i["id"]==plan["nodes"][u].get("artifact_id") and i.get("rev")!=plan["nodes"][u].get("rev") for i in node.get("inputs",[]))]
    if stale: return "stale"
    q=quality_map.get(artifact["id"],{})
    if any(r.get("state")=="FAIL" for r in q.get("results",[])): return "blocked"
    if any(r.get("state")=="HUMAN_REQUIRED" for r in q.get("results",[])): return "human-required"
    if artifact["status"] in ("approved","in-implementation","verified","released"): return "done"
    if artifact["status"] in ("proposed","reviewed"): return "in-review"
    return "draft"


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("command",choices=("plan","status","dispatch","report")); ap.add_argument("spec"); ap.add_argument("--registry",default=str(ROOT/"registry.json")); ap.add_argument("--authoring"); ap.add_argument("--repos",nargs="*",default=[]); ap.add_argument("--json",action="store_true"); ap.add_argument("--node"); ap.add_argument("--runner",choices=("orca","agent","print"),default="print")
    a=ap.parse_args(); spec=read_spec(a.spec); reg=load_registry(a.registry); plan=build(spec,reg,a.authoring)
    if a.command=="plan":
        if a.json: print(json.dumps(plan,indent=2))
        else:
            print(f"Workflow: {spec['title']} ({spec['id']})\nGoal: {spec['goal']}")
            for i,w in enumerate(plan["waves"],1): print(f"Wave {i}: " + ", ".join(w))
            for n in plan["nodes"].values(): print(f"  {n['id']}: {n['domain']} / {n['kind']} / {n['lead_skill']} -> {n['repo']}:{', '.join(n['paths'])}")
        return
    ids=[n.get("artifact_id") or n["id"] for n in plan["nodes"].values()]
    ids.extend(item["id"] for n in plan["nodes"].values() for item in n.get("inputs", []))
    q=quality(a.authoring,a.registry,a.repos,ids)
    states={nid:state_for(n,plan,q) for nid,n in plan["nodes"].items()}
    def inputs_ready(node):
        for item in node.get("inputs", []):
            if item["id"] in states:
                if states[item["id"]] != "done": return False
            else:
                source=plan["existing"].get(item["id"])
                if not source or source.get("status") not in ("approved", "in-implementation", "verified", "released"):
                    return False
                if item.get("rev") and item["rev"] != source.get("rev"):
                    return False
                if any(r.get("state") in ("FAIL", "HUMAN_REQUIRED") for r in q.get(item["id"], {}).get("results", [])):
                    return False
        return True
    if a.command=="dispatch":
        if not a.node or a.node not in plan["nodes"]: die("dispatch needs --node <known node id>")
        node=plan["nodes"][a.node]
        blockers=[e["from"] for e in plan["edges"] if e["to"]==a.node and states[e["from"]]!="done"]
        blockers.extend(i["id"] for i in node.get("inputs", []) if not inputs_ready({"inputs":[i]}))
        if blockers or states[a.node] not in ("missing","draft"):
            die(f"node {a.node} is not ready: " + (", ".join(blockers) if blockers else states[a.node]))
        contract={"node":node["id"],"domain":node["domain"],"lead_skill":node["lead_skill"],"artifact_kind":node["kind"],"output":node["paths"],"inputs":node["inputs"],"acceptance":node["acceptance"],"allowed_write_paths":node["paths"],"required_checks":node["checks"],"report":"workflow report"}
        body="Execute workflow node from this contract. Do not approve artifacts.\n"+json.dumps(contract,indent=2)
        if a.runner=="orca": body="orca orchestration worker-start --task " + json.dumps(body)
        elif a.runner=="agent": body="Agent task:\n"+body
        print(body); return
    revalidate=[]; stale_upstream=[]
    for nid,node in plan["nodes"].items():
        artifact=plan["existing"].get(node.get("artifact_id") or nid)
        if not artifact: continue
        recorded={x.get("id"):x.get("rev") for x in artifact.get("upstream",[]) if isinstance(x,dict)}
        changed=[up for up,rev in recorded.items() if up in plan["existing"] and rev != plan["existing"][up]["rev"]]
        if changed:
            states[nid]="stale"; stale_upstream.append({"node":nid,"upstream":changed})
            queue=[nid]
            while queue:
                current=queue.pop(0)
                for edge in plan["edges"]:
                    if edge["from"]==current and edge["to"] not in revalidate:
                        revalidate.append(edge["to"]); queue.append(edge["to"])
    if a.command=="status":
        out={"schema":"rpg-factory.workflow-status/1","states":states,"ready":[nid for nid,n in plan["nodes"].items() if states[nid] in ("missing","draft") and all(states[e["from"]]=="done" for e in plan["edges"] if e["to"]==nid) and inputs_ready(n)],"stale_upstream":stale_upstream,"revalidate":revalidate}
    else:
        overall="complete" if all(x=="done" for x in states.values()) and not revalidate else "incomplete"
        out={"schema":"rpg-factory.workflow-report/1","overall":overall,"nodes":{nid:{"artifact_id":n.get("artifact_id"),"rev":n.get("rev"),"status":states[nid],"quality":q.get(n.get("artifact_id") or nid),"reviews":[],"approvals":"HUMAN_REQUIRED" if states[nid]=="human-required" else "not recorded","engineering_trace":None} for nid,n in plan["nodes"].items()},"stale":revalidate,"blocked":[nid for nid,s in states.items() if s=="blocked"]}
    print(json.dumps(out,indent=2) if a.json else json.dumps(out,indent=2))


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
