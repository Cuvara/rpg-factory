"""Stable API for domain artifact quality plugins."""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
import importlib.util


@dataclass
class Result:
    check: str
    state: str
    reasons: list = field(default_factory=list)


@dataclass
class Context:
    repo: str
    registry: dict
    artifact_path: str
    artifacts: dict
    tools: object
    repo_roots: dict = field(default_factory=dict)

    def resolve_repo_path(self, repo, relative_path):
        """Resolve a registered repo-relative path, rejecting traversal and symlink escapes."""
        root = self.repo_roots.get(repo)
        if not root or not isinstance(relative_path, str) or not relative_path:
            return None
        rel = PurePosixPath(relative_path.replace("\\", "/"))
        if rel.is_absolute() or PureWindowsPath(relative_path).is_absolute() or PureWindowsPath(relative_path).drive or any(part in ("", ".", "..") for part in rel.parts):
            return None
        base = Path(root).resolve()
        candidate = (base / Path(*rel.parts)).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            return None
        return candidate

    def approval(self, artifact_id):
        """Verify the artifact's required signed approvals using artifact-trace rules."""
        pair = self.artifacts.get(artifact_id)
        if not pair:
            return {"state": "missing", "reasons": ["artifact is not available in this validation context"]}
        rel, artifact = pair if isinstance(pair, tuple) else (self.artifact_path, pair)
        life = self.registry.get("artifact_lifecycles", {}).get(artifact.get("kind"), self.registry.get("artifact_lifecycles", {}).get("default", {}))
        requirements = life.get("requirements", {}).get(artifact.get("status"), {})
        gates = list(requirements.get("needs_approval", []))
        conditional = requirements.get("approval_when_binding")
        if artifact.get("binding_values") is True and conditional:
            extra = conditional if isinstance(conditional, list) else self.registry.get("domains", {}).get(artifact.get("domain"), {}).get("human_gates", [])
            gates = list(dict.fromkeys(gates + extra))
        if not gates:
            return {"state": "missing", "reasons": ["no required approval is registered for this artifact state"]}
        spec = importlib.util.spec_from_file_location("artifact_trace_context", Path(__file__).resolve().parents[1] / "artifact-trace.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        reasons = []
        for gate in gates:
            reason = module.approval(self.repo, rel, artifact, gate, self.registry)
            if reason:
                reasons.append(f"{gate}: {reason}")
        if not reasons:
            return {"state": "verified", "reasons": ["required approval signatures are current and trusted"]}
        text = " ".join(reasons).lower()
        state = "untrusted" if any(x in text for x in ("trusted", "signature", "approver key", "principal")) else ("invalid" if any(x in text for x in ("invalid", "mismatch", "immutable", "date")) else "missing")
        return {"state": state, "reasons": reasons}
