"""Domain quality rules for production game design artifacts."""
import re
from domains._api import Result

ID = re.compile(r"^[A-Z]{2,5}-[a-z0-9-]+-[0-9]{3}$")

def check(artifact, ctx):
    out=[]; spec=artifact.get("spec",{}); kind=artifact.get("kind")
    def add(name, errors): out.append(Result("design-"+name, "FAIL" if errors else "PASS", errors))
    envelope=[]
    if artifact.get("schema_version",1)>=2:
        for key in ("authors","sources","spec"):
            if key not in artifact: envelope.append("version 2 artifact requires "+key)
    add("envelope",envelope)
    # Gameplay numbers are TBD/proposals unless this artifact has verified approval.
    errors=[]
    def walk(value,path="spec"):
        if isinstance(value,dict):
            if set(("value","status","rationale")) <= set(value) and value.get("status")=="proposal": return
            for k,v in value.items(): walk(v,path+"."+k)
        elif isinstance(value,(int,float)) and not isinstance(value,bool): errors.append(path+" has an unlabelled gameplay number")
        elif isinstance(value,list):
            for i,v in enumerate(value): walk(v,f"{path}[{i}]")
    walk(spec)
    if errors and artifact.get("binding_values") is True:
        approval_check=getattr(ctx,"approval",None)
        approval=approval_check(artifact.get("id")) if callable(approval_check) else {"state":"missing","reasons":[]}
        state=approval.get("state","missing") if isinstance(approval,dict) else "missing"
        reasons=approval.get("reasons",[]) if isinstance(approval,dict) else []
        if state=="verified":
            errors=[]
            add("numbers",errors)
        elif state=="missing":
            out.append(Result("design-numbers","HUMAN_REQUIRED",reasons or ["gameplay-rules approval is required for binding values"]))
        elif state in ("invalid","untrusted"):
            out.append(Result("design-numbers","FAIL",reasons or ["gameplay-rules approval is "+state]))
        else:
            out.append(Result("design-numbers","FAIL",reasons or ["gameplay-rules approval state is invalid: "+str(state)]))
    else:
        add("numbers",errors)
    known={aid:obj for aid,(_,obj) in ctx.artifacts.items()}
    references=[]
    if kind in ("feature-spec","gameplay-system","level-spec","quest-spec","npc-spec","item-spec"):
        references += ([spec.get("game_concept")] if spec.get("game_concept") else [])
        references += spec.get("gameplay_systems",[]) if isinstance(spec.get("gameplay_systems",[]),list) else []
        refs=artifact.get("sources",[])
        if kind!="gameplay-system" and not references and artifact.get("schema_version",1)>=2: errors=["references a game-concept/gameplay-system source"]
        else: errors=[]
        for ref in references:
            if ref not in known or known[ref].get("kind") not in ("game-concept","gameplay-system"): errors.append("unresolved design source "+str(ref))
        if kind in ("feature-spec","gameplay-system") and not refs and artifact.get("schema_version",1)>=2: errors.append("sources must list the referenced design artifact ids")
        for ref in refs:
            if ref not in known: errors.append("unresolved source "+str(ref))
        add("sources",errors)
    if kind=="gameplay-system" and isinstance(spec.get("economy"),dict):
        eco=spec["economy"]; errors=[]
        if not eco.get("currencies"): errors.append("economy currencies required")
        if not eco.get("sources"): errors.append("economy sources must be non-empty")
        if not eco.get("sinks"): errors.append("economy sinks must be non-empty")
        add("economy",errors)
    if kind in ("level-spec","quest-spec","npc-spec","item-spec"):
        errors=[]
        if not spec.get("content_refs"): errors.append("content_refs must identify existing content artifacts")
        for ref in spec.get("content_refs",[]):
            if ref not in known: errors.append("unknown content id "+str(ref))
            elif known[ref]["kind"] not in ("item-spec","npc-spec","level-spec"): errors.append("content reference must target item, NPC or level: "+str(ref))
        add("content-ids",errors)
        curve=spec.get("difficulty_curve")
        curve_values=[x.get("value") if isinstance(x,dict) else x for x in curve] if isinstance(curve,list) else []
        if isinstance(curve,list) and all(isinstance(x,(int,float)) for x in curve_values) and any(a>b for a,b in zip(curve_values,curve_values[1:])): errors=["difficulty curve must be monotonic"]
        else: errors=[]
        add("difficulty",errors)
    if kind=="technical-handoff":
        errors=[]
        for field in ("state_and_data_requirements","events_and_interactions","edge_cases","acceptance_criteria","engineering_dependencies"):
            if not spec.get(field): errors.append(field+" must be covered")
        if any(not isinstance(x,dict) or x.get("verify") not in ("test","review","measure") for x in spec.get("acceptance_criteria",[])):
            errors.append("each acceptance criterion needs a verify type")
        module_ids={m.get("id") for m in ctx.registry.get("modules",[])}
        repos=set(ctx.registry.get("repos",{}))
        modules=ctx.registry.get("modules",[])
        for dep in spec.get("engineering_dependencies",[]):
            if dep not in module_ids and ":" not in dep: errors.append("dependency must be a registered module id or repo:path: "+str(dep))
            elif ":" in dep:
                repo,path=dep.split(":",1)
                if repo not in repos: errors.append("unknown dependency repo: "+str(dep))
                elif not any(m.get("repo")==repo and any(path==p.rstrip("/") or path.startswith(p.rstrip("/")+"/") or p.rstrip("/").startswith(path.rstrip("/")+"/") for p in m.get("paths",[])) for m in modules): errors.append("dependency path is not registered: "+str(dep))
        add("technical-handoff",errors)
    return out
